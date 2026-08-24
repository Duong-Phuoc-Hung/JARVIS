"""
Dynamic Skill Synthesizer for JARVIS.
Transforms successfully verified code snippets into permanently packaged,
reusable, and introspectable skill modules with JSON schema metadata.
"""
from __future__ import annotations

import ast
import json
import logging
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Union

from jarvis.skills.models import SkillDefinition, SkillMetadata

logger = logging.getLogger("jarvis.skills.synthesizer")


class DynamicSkillSynthesizer:
    """
    Synthesizes and auto-packages Python code into persistent JARVIS skills.
    Generates standard module layouts, docstrings, metadata schemas, and documentation.
    """

    TYPE_MAP = {
        "str": "string",
        "int": "integer",
        "float": "number",
        "bool": "boolean",
        "list": "array",
        "List": "array",
        "dict": "object",
        "Dict": "object",
        "Any": "string",
        "Optional[str]": "string",
        "Optional[int]": "integer",
        "Optional[float]": "number",
        "Optional[bool]": "boolean",
        "Optional[List]": "array",
        "Optional[Dict]": "object",
    }

    def __init__(
        self,
        skills_dir: Optional[Union[str, Path]] = None,
        registry: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        self.registry = registry
        if skills_dir:
            self.skills_dir = Path(skills_dir).resolve()
        elif registry and hasattr(registry, "skills_dir"):
            self.skills_dir = Path(registry.skills_dir).resolve()
        else:
            self.skills_dir = Path(__file__).resolve().parent

        self.skills_dir.mkdir(parents=True, exist_ok=True)

    def extract_parameters_schema_from_code(
        self,
        code: str,
        function_name: str = "execute"
    ) -> Dict[str, Any]:
        """
        Inspect code AST to infer parameters schema and required fields from function signature.
        
        Args:
            code: Source code containing function definition.
            function_name: Name of entrypoint function to inspect.
            
        Returns:
            JSON schema dictionary describing inputs.
        """
        schema: Dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        try:
            tree = ast.parse(code)
        except Exception as exc:
            logger.warning("Could not parse AST to extract schema: %s", exc)
            return schema

        target_func: Optional[ast.FunctionDef] = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and (node.name == function_name or target_func is None):
                target_func = node
                if node.name == function_name:
                    break

        if not target_func:
            return schema

        args = target_func.args.args
        defaults = target_func.args.defaults
        num_defaults = len(defaults)
        num_args = len(args)
        default_offset = num_args - num_defaults

        for idx, arg in enumerate(args):
            arg_name = arg.arg
            if arg_name in ("self", "cls", "kwargs"):
                continue

            # Infer type annotation if present
            type_str = "string"
            if arg.annotation:
                try:
                    ann_str = ast.unparse(arg.annotation)
                    type_str = self.TYPE_MAP.get(ann_str, "string")
                except Exception:
                    type_str = "string"

            prop_def: Dict[str, Any] = {
                "type": type_str,
                "description": f"Parameter '{arg_name}'",
            }

            # Check if default value exists
            if idx >= default_offset:
                def_node = defaults[idx - default_offset]
                try:
                    def_val = ast.literal_eval(def_node)
                    prop_def["default"] = def_val
                except Exception:
                    pass
            else:
                schema["required"].append(arg_name)

            schema["properties"][arg_name] = prop_def

        return schema

    def format_skill_module(
        self,
        name: str,
        code: str,
        description: str,
        parameters_schema: Dict[str, Any],
        entrypoint_function: str = "execute",
    ) -> str:
        """
        Format code into standardized, standalone Python skill module with metadata docstrings.
        """
        clean_code = code.strip()

        # If code already defines the entrypoint function, wrap with header docstring
        has_entrypoint = bool(re.search(rf"\bdef\s+{entrypoint_function}\b", clean_code))

        if not has_entrypoint:
            # Wrap raw script code inside `def execute(**kwargs):`
            indented_code = "\n".join(f"    {line}" for line in clean_code.splitlines())
            formatted = f'''"""
JARVIS Persistent Skill: {name}
Description: {description}
Synthesized dynamically by JARVIS Agentic Superpower.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("jarvis.skills.{name}")


def {entrypoint_function}(**kwargs) -> Dict[str, Any]:
    """
    {description}
    """
{indented_code}
    return {{"status": "completed", "output": locals().get("result", "OK")}}
'''
        else:
            formatted = f'''"""
JARVIS Persistent Skill: {name}
Description: {description}
Synthesized dynamically by JARVIS Agentic Superpower.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("jarvis.skills.{name}")

{clean_code}
'''
        return formatted

    def synthesize_skill(
        self,
        name: str,
        code: str,
        description: str = "",
        parameters_schema: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        entrypoint_function: str = "execute",
        target_dir: Optional[Union[str, Path]] = None,
    ) -> SkillDefinition:
        """
        Synthesize, format, and package source code into a permanent SkillDefinition and save to disk.
        
        Args:
            name: Normalized skill identifier (e.g. 'csv_revenue_aggregator').
            code: Source code.
            description: Description of the skill capability.
            parameters_schema: Optional parameters schema (inferred if None).
            tags: Optional domain classification tags.
            entrypoint_function: Name of main entrypoint callable.
            target_dir: Optional override directory for skill storage.
            
        Returns:
            Packaged SkillDefinition instance.
        """
        # Normalize skill name
        clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", name.lower().strip()).strip("_")
        if not clean_name:
            clean_name = f"skill_{int(time.time())}"

        # Extract schema if not provided
        schema = parameters_schema or self.extract_parameters_schema_from_code(code, entrypoint_function)
        desc = description or f"Auto-synthesized skill {clean_name}"
        skill_tags = tags or ["synthesized", "autonomous"]

        formatted_code = self.format_skill_module(
            name=clean_name,
            code=code,
            description=desc,
            parameters_schema=schema,
            entrypoint_function=entrypoint_function,
        )

        metadata = SkillMetadata(
            name=clean_name,
            version="1.0.0",
            description=desc,
            parameters_schema=schema,
            tags=skill_tags,
            synthesized_by="jarvis_agentic_synthesizer",
            created_at=time.time(),
            updated_at=time.time(),
        )

        skill_def = SkillDefinition(
            metadata=metadata,
            entrypoint_code=formatted_code,
            entrypoint_function=entrypoint_function,
        )

        # Save to disk
        save_path = self.package_and_save(skill_def, target_dir)
        skill_def.file_path = str(save_path)

        logger.info("Successfully synthesized and saved skill '%s' to '%s'", clean_name, save_path)
        return skill_def

    def package_and_save(
        self,
        skill_def: SkillDefinition,
        target_dir: Optional[Union[str, Path]] = None,
    ) -> Path:
        """
        Save skill module file, metadata.json, and SKILL.md into package directory.
        
        Returns:
            Path to the main Python module entrypoint.
        """
        base_dir = Path(target_dir).resolve() if target_dir else self.skills_dir
        skill_dir = base_dir / skill_def.metadata.name
        skill_dir.mkdir(parents=True, exist_ok=True)

        # 1. Write Python module: __init__.py
        module_file = skill_dir / "__init__.py"
        module_file.write_text(skill_def.entrypoint_code, encoding="utf-8")

        # 2. Write metadata.json
        meta_file = skill_dir / "metadata.json"
        meta_file.write_text(
            json.dumps(skill_def.metadata.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # 3. Write human-readable SKILL.md
        skill_md = skill_dir / "SKILL.md"
        md_content = f"""# Skill: {skill_def.metadata.name}

## Description
{skill_def.metadata.description}

- **Version**: {skill_def.metadata.version}
- **Synthesized By**: {skill_def.metadata.synthesized_by}
- **Tags**: {", ".join(skill_def.metadata.tags)}

## Parameters Schema
```json
{json.dumps(skill_def.metadata.parameters_schema, indent=2)}
```
"""
        skill_md.write_text(md_content, encoding="utf-8")

        return module_file
