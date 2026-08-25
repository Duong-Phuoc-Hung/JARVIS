"""
Persistent Skill Registry and Dynamic Importer for JARVIS.
Discovers, dynamically loads, validates, and manages execution of
persistent skills, with seamless ActionDispatcher integration and telemetry.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
from pathlib import Path
import shutil
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Union

from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.models import PrivilegeLevel
from jarvis.skills.models import SkillDefinition, SkillExecutionResult, SkillMetadata

logger = logging.getLogger("jarvis.skills.registry")


class SkillRegistry:
    """
    Manages persistent skill discovery, dynamic loading, execution,
    telemetry persistence, and ActionDispatcher registration.
    """

    BUILTIN_FILES: Set[str] = {
        "__init__.py",
        "models.py",
        "registry.py",
        "synthesizer.py",
    }

    def __init__(
        self,
        skills_dir: Optional[Union[str, Path]] = None,
        dispatcher: Optional[ActionDispatcher] = None,
        auto_discover: bool = True,
    ) -> None:
        if skills_dir:
            self.skills_dir = Path(skills_dir).resolve()
        else:
            self.skills_dir = Path(__file__).resolve().parent

        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.dispatcher = dispatcher
        self._skills: Dict[str, SkillDefinition] = {}
        self._lock = threading.RLock()

        if auto_discover:
            self.discover_skills()

    def discover_skills(self) -> Dict[str, SkillDefinition]:
        """
        Scan skills directory, discovering and loading all packaged skills.
        
        Returns:
            Dictionary mapping skill_name to loaded SkillDefinition.
        """
        discovered: Dict[str, SkillDefinition] = {}
        if not self.skills_dir.exists():
            return discovered

        with self._lock:
            # 1. Look for subdirectories containing metadata.json or __init__.py
            for entry in self.skills_dir.iterdir():
                if entry.is_dir() and not entry.name.startswith((".", "__")):
                    skill_name = entry.name
                    loaded_def = self.load_skill_from_directory(entry)
                    if loaded_def:
                        discovered[skill_name] = loaded_def
                        self._skills[skill_name] = loaded_def

            # 2. Look for standalone Python files (e.g. `my_skill.py`)
            for entry in self.skills_dir.glob("*.py"):
                if entry.name not in self.BUILTIN_FILES and not entry.name.startswith((".", "__")):
                    skill_name = entry.stem
                    if skill_name not in discovered:
                        loaded_def = self.load_skill_from_file(entry)
                        if loaded_def:
                            discovered[skill_name] = loaded_def
                            self._skills[skill_name] = loaded_def

            # Register into dispatcher if configured
            if self.dispatcher:
                self.register_all_into_dispatcher()

        logger.info("SkillRegistry discovered %d skills in '%s'", len(discovered), self.skills_dir)
        return discovered

    def load_skill_from_directory(self, skill_dir: Path) -> Optional[SkillDefinition]:
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
                metadata = SkillMetadata.from_dict(meta_dict)
            except Exception as exc:
                logger.warning("Failed to parse metadata.json in '%s': %s", skill_dir, exc)

        if not metadata:
            metadata = SkillMetadata(
                name=skill_dir.name,
                description=f"Persistent skill {skill_dir.name}",
            )

        return self._import_skill_module(
            skill_name=metadata.name,
            file_path=entry_file,
            metadata=metadata,
        )

    def load_skill_from_file(self, file_path: Path) -> Optional[SkillDefinition]:
        """Load a skill defined in a standalone Python file."""
        skill_name = file_path.stem
        meta_file = file_path.parent / f"{skill_name}.json"
        
        metadata = None
        if meta_file.exists():
            try:
                meta_dict = json.loads(meta_file.read_text(encoding="utf-8"))
                metadata = SkillMetadata.from_dict(meta_dict)
            except Exception as exc:
                logger.warning("Failed to parse %s.json: %s", skill_name, exc)

        if not metadata:
            metadata = SkillMetadata(
                name=skill_name,
                description=f"Standalone skill {skill_name}",
            )

        return self._import_skill_module(
            skill_name=skill_name,
            file_path=file_path,
            metadata=metadata,
        )

    def _import_skill_module(
        self,
        skill_name: str,
        file_path: Path,
        metadata: SkillMetadata,
        entrypoint_function: str = "execute",
    ) -> Optional[SkillDefinition]:
        """Dynamically import a Python file and validate its execute entrypoint."""
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
        with self._lock:
            if not skill_def.is_loaded and skill_def.entrypoint_code:
                # If not yet imported, save and load
                skill_dir = self.skills_dir / name
                skill_dir.mkdir(parents=True, exist_ok=True)
                module_file = skill_dir / "__init__.py"
                module_file.write_text(skill_def.entrypoint_code, encoding="utf-8")
                
                meta_file = skill_dir / "metadata.json"
                meta_file.write_text(
                    json.dumps(skill_def.metadata.to_dict(), indent=2, ensure_ascii=False),
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

    def get_skill(self, skill_name: str) -> Optional[SkillDefinition]:
        """Retrieve loaded skill by name."""
        with self._lock:
            return self._skills.get(skill_name)

    def load_skill(self, skill_name: str) -> Optional[SkillDefinition]:
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

    def reload_skill(self, skill_name: str) -> Optional[SkillDefinition]:
        """Hot-reload an existing skill from disk."""
        return self.load_skill(skill_name)

    def list_skills(self) -> List[SkillMetadata]:
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

        # Update telemetry
        skill_def.metadata.record_invocation(success=success, latency_ms=elapsed)
        self._persist_skill_metadata(skill_def)

        return SkillExecutionResult(
            skill_name=skill_name,
            success=success,
            data=data,
            artifacts=artifacts,
            error=error,
            execution_time_ms=elapsed,
        )

    def _persist_skill_metadata(self, skill_def: SkillDefinition) -> None:
        """Save updated skill telemetry to metadata.json on disk."""
        if not skill_def.file_path:
            return

        try:
            file_path = Path(skill_def.file_path)
            if file_path.parent.name == skill_def.metadata.name:
                meta_file = file_path.parent / "metadata.json"
            else:
                meta_file = file_path.parent / f"{skill_def.metadata.name}.json"

            meta_file.write_text(
                json.dumps(skill_def.metadata.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Failed to persist metadata for skill '%s': %s", skill_def.metadata.name, exc)

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

    def register_all_into_dispatcher(self, dispatcher: Optional[ActionDispatcher] = None) -> int:
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

    def get_metrics(self, skill_name: Optional[str] = None) -> Dict[str, Any]:
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
