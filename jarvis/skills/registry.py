"""
Persistent Skill Registry and Dynamic Importer for JARVIS.
Discovers, dynamically loads, validates, and manages execution of
persistent skills, with seamless ActionDispatcher integration and telemetry.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import shutil
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.models import PrivilegeLevel
from jarvis.skills.models import SkillDefinition, SkillExecutionResult, SkillMetadata
from jarvis.skills.telemetry import SkillTelemetryStore, default_telemetry_path_for
from jarvis.skills.validation import is_safe_entrypoint_identifier, is_safe_skill_identifier

logger = logging.getLogger("jarvis.skills.registry")


class SkillRegistry:
    """
    Manages persistent skill discovery, dynamic loading, execution,
    telemetry persistence, and ActionDispatcher registration.
    """

    BUILTIN_FILES: set[str] = {
        "__init__.py",
        "models.py",
        "registry.py",
        "synthesizer.py",
    }

    def __init__(
        self,
        skills_dir: str | Path | None = None,
        dispatcher: ActionDispatcher | None = None,
        auto_discover: bool = True,
        telemetry_store: SkillTelemetryStore | None = None,
    ) -> None:
        if skills_dir:
            self.skills_dir = Path(skills_dir).resolve()
        else:
            self.skills_dir = Path(__file__).resolve().parent

        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.dispatcher = dispatcher
        self._skills: dict[str, SkillDefinition] = {}
        self._lock = threading.RLock()
        # Runtime invocation telemetry lives outside the packaged skill tree
        # (see jarvis.skills.telemetry) -- injectable for deterministic
        # tests; defaults to a file under JARVIS's writable per-user data
        # dir, scoped to this specific skills_dir (so normal invocation
        # never rewrites packaged jarvis/skills/*/metadata.json, and a
        # fresh temporary skills_dir in a test never inherits telemetry
        # from another test run or the real packaged tree).
        self.telemetry = telemetry_store or SkillTelemetryStore(store_path=default_telemetry_path_for(self.skills_dir))

        if auto_discover:
            self.discover_skills()

    def discover_skills(self) -> dict[str, SkillDefinition]:
        """
        Scan skills directory, discovering and loading all packaged skills.

        Discovery order is deterministic (sorted by name) so repeated calls
        and duplicate-name resolution behave the same way every run,
        regardless of filesystem iteration order. A single malformed or
        unsafe skill is skipped (logged) without aborting discovery of the
        rest. If a skill's own declared metadata name collides with an
        already-discovered skill from this same call, the first one
        (sorted order) wins and the duplicate is skipped with a warning --
        never a silent overwrite.

        Returns:
            Dictionary mapping skill_name to loaded SkillDefinition.
        """
        discovered: dict[str, SkillDefinition] = {}
        if not self.skills_dir.exists():
            return discovered

        with self._lock:
            # 1. Look for subdirectories containing metadata.json or __init__.py
            dir_entries = sorted(
                (e for e in self.skills_dir.iterdir() if e.is_dir() and not e.name.startswith((".", "__"))),
                key=lambda p: p.name,
            )
            for entry in dir_entries:
                loaded_def = self.load_skill_from_directory(entry)
                if not loaded_def:
                    continue
                resolved_name = loaded_def.metadata.name
                if resolved_name in discovered:
                    logger.warning(
                        "Duplicate skill name '%s' from directory '%s' ignored "
                        "(already discovered from an earlier entry this run).",
                        resolved_name,
                        entry,
                    )
                    continue
                discovered[resolved_name] = loaded_def
                self._skills[resolved_name] = loaded_def

            # 2. Look for standalone Python files (e.g. `my_skill.py`)
            file_entries = sorted(
                (
                    e
                    for e in self.skills_dir.glob("*.py")
                    if e.name not in self.BUILTIN_FILES and not e.name.startswith((".", "__"))
                ),
                key=lambda p: p.name,
            )
            for entry in file_entries:
                skill_name = entry.stem
                if skill_name in discovered:
                    continue
                loaded_def = self.load_skill_from_file(entry)
                if not loaded_def:
                    continue
                resolved_name = loaded_def.metadata.name
                if resolved_name in discovered:
                    logger.warning(
                        "Duplicate skill name '%s' from file '%s' ignored "
                        "(already discovered from an earlier entry this run).",
                        resolved_name,
                        entry,
                    )
                    continue
                discovered[resolved_name] = loaded_def
                self._skills[resolved_name] = loaded_def

            # Register into dispatcher if configured
            if self.dispatcher:
                self.register_all_into_dispatcher()

        logger.info("SkillRegistry discovered %d skills in '%s'", len(discovered), self.skills_dir)
        return discovered

    def load_skill_from_directory(self, skill_dir: Path) -> SkillDefinition | None:
        """Load a skill packaged in a sub-folder."""
        metadata_file = skill_dir / "metadata.json"
        entry_file = skill_dir / "__init__.py"

        if not entry_file.exists():
            # Check for <skill_name>.py inside directory
            alt_entry = skill_dir / f"{skill_dir.name}.py"
            if alt_entry.exists():
                entry_file = alt_entry
            else:
                logger.warning("No entrypoint file found in skill folder '%s'", skill_dir)
                return None

        metadata = None
        if metadata_file.exists():
            try:
                meta_dict = json.loads(metadata_file.read_text(encoding="utf-8"))
                meta_dict = self._sanitize_declared_name(meta_dict, fallback_name=skill_dir.name)
                metadata = SkillMetadata.from_dict(meta_dict)
            except Exception as exc:
                logger.warning("Failed to parse metadata.json in '%s': %s", skill_dir, exc)

        if not metadata:
            metadata = SkillMetadata(
                name=skill_dir.name,
                description=f"Persistent skill {skill_dir.name}",
            )

        self._enforce_safe_skill_name(metadata, fallback_name=skill_dir.name)
        self._hydrate_telemetry(metadata)

        return self._import_skill_module(
            skill_name=metadata.name,
            file_path=entry_file,
            metadata=metadata,
        )

    def load_skill_from_file(self, file_path: Path) -> SkillDefinition | None:
        """Load a skill defined in a standalone Python file."""
        skill_name = file_path.stem
        meta_file = file_path.parent / f"{skill_name}.json"

        metadata = None
        if meta_file.exists():
            try:
                meta_dict = json.loads(meta_file.read_text(encoding="utf-8"))
                meta_dict = self._sanitize_declared_name(meta_dict, fallback_name=skill_name)
                metadata = SkillMetadata.from_dict(meta_dict)
            except Exception as exc:
                logger.warning("Failed to parse %s.json: %s", skill_name, exc)

        if not metadata:
            metadata = SkillMetadata(
                name=skill_name,
                description=f"Standalone skill {skill_name}",
            )

        self._enforce_safe_skill_name(metadata, fallback_name=skill_name)
        self._hydrate_telemetry(metadata)

        return self._import_skill_module(
            skill_name=metadata.name,
            file_path=file_path,
            metadata=metadata,
        )

    @staticmethod
    def _sanitize_declared_name(meta_dict: Any, fallback_name: str) -> Any:
        """
        Runs BEFORE SkillMetadata.from_dict(). A declared "name" that is
        missing, the wrong type, or an unsafe string must never be allowed
        to reach from_dict()'s own type coercion: from_dict() has no
        filesystem-derived fallback to use, so a wrong-TYPED name (e.g.
        `"name": 12345`) would otherwise coerce to the fixed generic
        placeholder "unnamed_skill" -- a value that is itself a *safe
        identifier string* and would therefore silently pass
        _enforce_safe_skill_name()'s later check unchanged, letting an
        invalid name masquerade as a real (and potentially collision-prone,
        shared-across-skills) identity instead of failing back to this
        skill's own correct, safe, filesystem-derived name. Substituting
        the fallback here, before construction, means the skill's identity
        can never silently become a generic placeholder or another skill's
        name -- only ever its own correct name.
        """
        if not isinstance(meta_dict, dict):
            return meta_dict
        if not is_safe_skill_identifier(meta_dict.get("name")):
            if "name" in meta_dict:
                logger.warning(
                    "Skill metadata declared invalid/unsafe name %r; using filesystem-derived name '%s' instead.",
                    meta_dict.get("name"),
                    fallback_name,
                )
            meta_dict = dict(meta_dict)
            meta_dict["name"] = fallback_name
        return meta_dict

    @staticmethod
    def _enforce_safe_skill_name(metadata: SkillMetadata, fallback_name: str) -> None:
        """
        A skill's declared metadata.name is untrusted content (it comes from
        a JSON file the skill's own directory owns) and later gets used to
        construct filesystem paths (register_skill()). If it isn't a safe
        identifier -- e.g. contains path separators or '..' -- fall back to
        the filesystem-derived name (guaranteed safe, since it came from an
        actual directory/file entry) rather than trusting it, so an unsafe
        value can never propagate into path construction. The skill still
        loads; only the untrusted name is overridden.
        """
        if not is_safe_skill_identifier(metadata.name):
            logger.warning(
                "Skill metadata declared unsafe name %r; using filesystem-derived name '%s' instead.",
                metadata.name,
                fallback_name,
            )
            metadata.name = fallback_name

    def _hydrate_telemetry(self, metadata: SkillMetadata) -> None:
        """
        Overlay persisted runtime telemetry (if any) from the separate
        telemetry store onto freshly-parsed static metadata. If the store
        has no entry yet for this skill, the metadata's own values (e.g.
        historical counters still present in an old-style packaged
        metadata.json) are left untouched -- telemetry is never silently
        reset to zero merely because the store hasn't been written to yet.
        """
        stats = self.telemetry.get(metadata.name)
        if not stats:
            return
        metadata.invocation_count = int(stats.get("invocation_count", metadata.invocation_count))
        metadata.success_count = int(stats.get("success_count", metadata.success_count))
        metadata.failure_count = int(stats.get("failure_count", metadata.failure_count))
        metadata.total_latency_ms = float(stats.get("total_latency_ms", metadata.total_latency_ms))
        metadata.updated_at = float(stats.get("updated_at", metadata.updated_at))

    def _import_skill_module(
        self,
        skill_name: str,
        file_path: Path,
        metadata: SkillMetadata,
        entrypoint_function: str = "execute",
    ) -> SkillDefinition | None:
        """Dynamically import a Python file and validate its execute entrypoint."""
        if not is_safe_entrypoint_identifier(entrypoint_function):
            logger.error(
                "Refusing to load skill '%s': unsafe entrypoint identifier %r", skill_name, entrypoint_function
            )
            return None
        try:
            module_name = f"jarvis_dynamic_skill_{skill_name}"
            spec = importlib.util.spec_from_file_location(module_name, str(file_path))
            if not spec or not spec.loader:
                logger.error("Could not create import spec for '%s'", file_path)
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            handler = getattr(module, entrypoint_function, None)
            if not handler or not callable(handler):
                logger.warning(
                    "Skill '%s' at '%s' is missing callable '%s' entrypoint",
                    skill_name,
                    file_path,
                    entrypoint_function,
                )
                return None

            entrypoint_code = ""
            try:
                entrypoint_code = file_path.read_text(encoding="utf-8")
            except Exception:
                pass

            skill_def = SkillDefinition(
                metadata=metadata,
                entrypoint_code=entrypoint_code,
                entrypoint_function=entrypoint_function,
                file_path=str(file_path),
                is_loaded=True,
                handler=handler,
            )
            return skill_def

        except Exception as exc:
            logger.error("Failed to dynamically import skill '%s': %s", skill_name, exc, exc_info=True)
            return None

    def register_skill(self, skill_def: SkillDefinition, save_to_disk: bool = True) -> bool:
        """
        Register a new skill in-memory, write to disk if needed, and register to dispatcher.
        
        Args:
            skill_def: The SkillDefinition to register.
            save_to_disk: Whether to persist module code and metadata to disk.
            
        Returns:
            True if registration succeeded.
        """
        name = skill_def.metadata.name
        if not is_safe_skill_identifier(name):
            logger.error("Refusing to register skill with unsafe identifier %r", name)
            return False

        with self._lock:
            if not skill_def.is_loaded and skill_def.entrypoint_code:
                # If not yet imported, save and load
                skill_dir = self.skills_dir / name
                skill_dir.mkdir(parents=True, exist_ok=True)
                module_file = skill_dir / "__init__.py"
                module_file.write_text(skill_def.entrypoint_code, encoding="utf-8")

                meta_file = skill_dir / "metadata.json"
                meta_file.write_text(
                    json.dumps(skill_def.metadata.to_manifest_dict(), indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )

                loaded = self._import_skill_module(name, module_file, skill_def.metadata)
                if not loaded:
                    return False
                skill_def = loaded

            self._skills[name] = skill_def

            if self.dispatcher:
                self._register_skill_to_dispatcher(skill_def)

        logger.info("Successfully registered skill '%s'", name)
        return True

    def unregister_skill(self, skill_name: str, remove_from_disk: bool = False) -> bool:
        """Remove a skill from the registry and optionally delete from disk."""
        with self._lock:
            skill_def = self._skills.pop(skill_name, None)
            if not skill_def:
                return False

            if self.dispatcher:
                self.dispatcher.unregister_action(f"skill_{skill_name}")

            if remove_from_disk and skill_def.file_path:
                try:
                    path = Path(skill_def.file_path)
                    if path.parent.name == skill_name and path.parent != self.skills_dir:
                        shutil.rmtree(path.parent, ignore_errors=True)
                    elif path.exists():
                        path.unlink(missing_ok=True)
                        meta = path.parent / f"{skill_name}.json"
                        meta.unlink(missing_ok=True)
                except Exception as exc:
                    logger.warning("Failed to remove skill files from disk: %s", exc)

        logger.info("Unregistered skill '%s'", skill_name)
        return True

    def get_skill(self, skill_name: str) -> SkillDefinition | None:
        """Retrieve loaded skill by name."""
        with self._lock:
            return self._skills.get(skill_name)

    def load_skill(self, skill_name: str) -> SkillDefinition | None:
        """Load or reload skill by name."""
        with self._lock:
            skill_dir = self.skills_dir / skill_name
            if skill_dir.is_dir():
                loaded = self.load_skill_from_directory(skill_dir)
                if loaded:
                    self._skills[skill_name] = loaded
                    if self.dispatcher:
                        self._register_skill_to_dispatcher(loaded)
                    return loaded

            skill_file = self.skills_dir / f"{skill_name}.py"
            if skill_file.is_file():
                loaded = self.load_skill_from_file(skill_file)
                if loaded:
                    self._skills[skill_name] = loaded
                    if self.dispatcher:
                        self._register_skill_to_dispatcher(loaded)
                    return loaded

            return self._skills.get(skill_name)

    def reload_skill(self, skill_name: str) -> SkillDefinition | None:
        """Hot-reload an existing skill from disk."""
        return self.load_skill(skill_name)

    def list_skills(self) -> list[SkillMetadata]:
        """Return list of all registered skill metadata objects."""
        with self._lock:
            return [s.metadata for s in self._skills.values()]

    def invoke_skill(self, skill_name: str, **kwargs) -> SkillExecutionResult:
        """
        Directly invoke a loaded skill by name with arguments and update usage metrics.
        
        Args:
            skill_name: Name of registered skill.
            **kwargs: Keyword arguments for entrypoint function.
            
        Returns:
            SkillExecutionResult with execution data, status, and latency.
        """
        skill_def = self.get_skill(skill_name)
        if not skill_def or not skill_def.handler:
            return SkillExecutionResult(
                skill_name=skill_name,
                success=False,
                error=f"Skill '{skill_name}' is not registered or not loaded.",
            )

        t0 = time.perf_counter()
        success = False
        data = None
        error = None
        artifacts = []

        try:
            raw_res = skill_def.handler(**kwargs)
            success = True
            if isinstance(raw_res, dict):
                data = raw_res.get("data", raw_res.get("output", raw_res))
                artifacts = raw_res.get("artifacts", [])
            else:
                data = raw_res
        except Exception as exc:
            success = False
            error = str(exc)
            logger.error("Error executing skill '%s': %s", skill_name, exc, exc_info=True)

        elapsed = max((time.perf_counter() - t0) * 1000.0, 0.01)

        # Update telemetry. The in-memory SkillMetadata is updated as before
        # (preserves get_metrics()/success_rate/avg_latency_ms behavior for
        # this process's lifetime); persistence goes to the separate
        # telemetry store, NEVER back into the packaged metadata.json --
        # normal skill invocation must not mutate tracked source manifests.
        # `seed` bootstraps the store from this skill's current in-memory
        # counters (pre-increment) the first time the store has no entry
        # for it yet, so any historical counters already baked into an
        # old-style packaged metadata.json are carried forward instead of
        # silently resetting to zero the moment the store takes over.
        #
        # The seed-capture + in-memory increment must be one atomic section:
        # skill_def.metadata is one shared object across every caller of
        # invoke_skill() for this skill, and record_invocation()'s `+= 1` is
        # a read-modify-write on a plain attribute -- not atomic on its own.
        # Without this lock, concurrent invocations of the same skill could
        # lose updates (classic lost-update race). The registry's own RLock
        # is reused here (already used by discover_skills()/register_skill());
        # the disk write itself is intentionally done outside this lock --
        # SkillTelemetryStore has its own independent lock and derives each
        # increment from whatever is currently on disk, not from `seed`
        # (seed only ever bootstraps a skill's very first store entry), so
        # the two locks never need to be unified for correctness.
        with self._lock:
            seed = {
                "invocation_count": skill_def.metadata.invocation_count,
                "success_count": skill_def.metadata.success_count,
                "failure_count": skill_def.metadata.failure_count,
                "total_latency_ms": skill_def.metadata.total_latency_ms,
            }
            skill_def.metadata.record_invocation(success=success, latency_ms=elapsed)
        self.telemetry.record_invocation(skill_def.metadata.name, success=success, latency_ms=elapsed, seed=seed)

        return SkillExecutionResult(
            skill_name=skill_name,
            success=success,
            data=data,
            artifacts=artifacts,
            error=error,
            execution_time_ms=elapsed,
        )

    def _create_dispatcher_handler(self, skill_name: str) -> Callable[..., Any]:
        """Create ActionDispatcher adapter for a skill."""
        def _handler(**kwargs) -> Any:
            res = self.invoke_skill(skill_name, **kwargs)
            if not res.success:
                raise RuntimeError(res.error or f"Skill '{skill_name}' execution failed.")
            return res.data
        return _handler

    def _register_skill_to_dispatcher(self, skill_def: SkillDefinition) -> None:
        """Register a single skill into ActionDispatcher."""
        if not self.dispatcher:
            return

        action_name = f"skill_{skill_def.metadata.name}"
        handler = self._create_dispatcher_handler(skill_def.metadata.name)

        self.dispatcher.register_action(
            name=action_name,
            handler=handler,
            required_privilege=PrivilegeLevel.NORMAL,
            description=skill_def.metadata.description,
            schema=skill_def.metadata.parameters_schema,
        )
        logger.debug("Registered skill action '%s' into ActionDispatcher", action_name)

    def register_all_into_dispatcher(self, dispatcher: ActionDispatcher | None = None) -> int:
        """Register all loaded skills into the provided or configured ActionDispatcher."""
        disp = dispatcher or self.dispatcher
        if not disp:
            return 0

        self.dispatcher = disp
        count = 0
        with self._lock:
            for skill_def in self._skills.values():
                if skill_def.is_loaded:
                    self._register_skill_to_dispatcher(skill_def)
                    count += 1
        return count

    def get_metrics(self, skill_name: str | None = None) -> dict[str, Any]:
        """Get telemetry metrics for a specific skill or all skills."""
        with self._lock:
            if skill_name:
                skill = self._skills.get(skill_name)
                if not skill:
                    return {}
                return {
                    "name": skill.metadata.name,
                    "invocations": skill.metadata.invocation_count,
                    "success_count": skill.metadata.success_count,
                    "failure_count": skill.metadata.failure_count,
                    "success_rate": skill.metadata.success_rate,
                    "avg_latency_ms": skill.metadata.avg_latency_ms,
                }

            total_invocations = sum(s.metadata.invocation_count for s in self._skills.values())
            total_success = sum(s.metadata.success_count for s in self._skills.values())
            total_failure = sum(s.metadata.failure_count for s in self._skills.values())

            return {
                "total_skills": len(self._skills),
                "total_invocations": total_invocations,
                "total_success": total_success,
                "total_failure": total_failure,
                "skills": {
                    name: {
                        "invocations": s.metadata.invocation_count,
                        "success_rate": s.metadata.success_rate,
                        "avg_latency_ms": s.metadata.avg_latency_ms,
                    }
                    for name, s in self._skills.items()
                },
            }
