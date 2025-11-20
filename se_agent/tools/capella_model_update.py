# se_agent/tools/export_capella_update.py
from se_agent.core.tool_patterns import  TransformTool
from capellambse import decl
import io, yaml
import capellambse
from capellambse.metamodel.cs import Part

class CapellaModelUpdateTool(TransformTool):
    """
    Transform: Apply updates from a hierarchy artifact to selected objects in a Capella model.

    Inputs:
      • selection_name: name of a 'capella_selection' artifact containing UUIDs
      • model_path_name: name of a 'capella_model_path' artifact (.aird file)
      • resources_name: name of a 'resources' artifact (folder dict)
      • hierarchy_name: name of a 'hierarchy' artifact containing structured updates
      • apply_mode: optional, one of ['update', 'create', 'sync'] (default='update')

    Behavior:
      • Loads the Capella model
      • Finds selected objects
      • Applies updates from hierarchy content
      • Saves/syncs the model
      • Returns an 'update_log' artifact with the changes made
    """

    name = "capella_model_update"
    description = (
        "Apply updates or create new elements in a Capella model using hierarchy data. "
        "This tool connects to the model specified by 'model_path_name' and 'resources_name', "
        "and uses a 'capella_selection' artifact to identify target objects. "
        "In 'update' mode (default), it modifies existing elements according to hierarchy content. "
        "In 'create' mode, it treats the current selection as the parent object "
        "and automatically determines whether to create Logical Components or Logical Functions "
        "based on the parent's type. For Logical Components, both a component and a part are created; "
        "for Logical Functions, a single function is created. "
        "The tool uses capellambse.decl.apply() to perform YAML-based updates and model insertions. "
        "An 'update_log' artifact is produced summarizing created or modified objects. "
        "Inputs: 'selection_name', 'model_path_name', 'resources_name', 'hierarchy_name', "
        "and optional 'apply_mode' ('update', 'create', or 'sync'). "
        "Example action: "
        "{\"actions\":[{\"tool\":\"export_capella_update\",\"input\":{"
        "\"selection_name\":\"EngineSystem\",\"model_path_name\":\"Bike_Path\","
        "\"resources_name\":\"Bike_Resources\",\"hierarchy_name\":\"Engine_Subsystem\","
        "\"apply_mode\":\"create\"}}]}"
    )


class ExportCapellaUpdateTool(TransformTool):
    name = "export_capella_update"
    artifact_type = "update_log"

    def transform(self, input_data, artifacts, package_name=None):
        pkg = package_name or getattr(artifacts, "active_package", None)
        model_path = artifacts.get_artifact(pkg, name=input_data["model_path_name"]).content
        resources  = artifacts.get_artifact(pkg, name=input_data["resources_name"]).content
        selection  = artifacts.get_artifact(pkg, name=input_data["selection_name"]).content
        hierarchy  = artifacts.get_artifact(pkg, name=input_data["hierarchy_name"]).content
        mode       = input_data.get("apply_mode", "update").lower()

        model = capellambse.MelodyModel(model_path, resources=resources)
        la_model = model.la  # could also be model.sa, model.pa, etc.

        log = []

        if mode == "create":
            # Selection is single parent object
            parent_uuid = selection[0]["uuid"]
            parent_obj = model.by_uuid(parent_uuid)
            parent_type = type(parent_obj).__name__

            created = self.apply_hierarchy_create(model, parent_obj, hierarchy)
            log.extend(created)
            ui_summary = f"Created {len(created)} new object(s) under {parent_obj.name} ({parent_type})."

        else:
            updated = self.apply_hierarchy_updates(model, hierarchy)
            log.extend(updated)
            ui_summary = f"Updated {len(updated)} existing object(s) in model '{model_path}'."

        # Save model
        try:
            model.save()
        except Exception as e:
            log.append(f"❌ Save failed: {e}")

        metadata = {"ui_summary": ui_summary, "mode": mode, "count": len(log)}
        return {"update_log": log}, metadata

    # ---------------------------------------------------------
    # 👇 Helpers for update/create modes
    # ---------------------------------------------------------

    def apply_hierarchy_create(self, model, parent_obj, hierarchy):
        """Create Components or Functions under the given parent object based on its Capella type."""
        results = []
    
        # Retrieve Capella metaclass name, falling back to Python class if needed
        try:
            parent_type = getattr(parent_obj, "type", None) or getattr(parent_obj, "eClass", None) or type(parent_obj).__name__
            parent_type_str = str(parent_type)
        except Exception:
            parent_type_str = type(parent_obj).__name__
    
        # Normalize for easy comparisons
        parent_type_str = parent_type_str.replace(" ", "").replace("_", "-")
    
        # -------------------------
        # Type classification rules
        # -------------------------
        is_component_parent = any(
            kw in parent_type_str
            for kw in (
                "LogicalComponent",
                "SystemComponent",
                "PhysicalComponent-BEHAVIOR",
                "PhysicalComponent-NODE",
            )
        )
        is_function_parent = any(
            kw in parent_type_str
            for kw in (
                "SystemFunction",
                "LogicalFunction",
                "PhysicalFunction",
            )
        )
    
        # -------------------------
        # Creation logic
        # -------------------------
        for item in hierarchy:
            name = item.get("name")
            if not name:
                continue
    
            try:
                if is_function_parent:
                    self.create_logical_function(model, parent_obj, item)
                    results.append(f"✅ Created Function '{name}' under '{parent_obj.name}'")
    
                elif is_component_parent:
                    new_comp = self.create_logical_component(model, parent_obj, item)
                    self.add_part_to_component(model, parent_obj, item, new_comp)
                    results.append(f"✅ Created Component '{name}' under '{parent_obj.name}'")
    
                else:
                    results.append(f"⚠️ Unsupported parent type '{parent_type_str}' for creation under '{parent_obj.name}'")
    
            except Exception as e:
                results.append(f"❌ Failed to create '{name}' under '{parent_obj.name}': {e}")
    
        return results


    def apply_hierarchy_updates(self, model, hierarchy):
        """Stub for now — implement per your YAML update logic."""
        return [f"Updated hierarchy with {len(hierarchy)} records (placeholder)."]

    # --- Inline your existing creation helpers -----------------------

    def create_logical_component(self, model, root_component, component):
        """Create a LogicalComponent under the specified root_component."""
        yaml.add_constructor("!uuid", lambda loader, node: loader.construct_scalar(node), Loader=yaml.SafeLoader)
        model_update = f"""
- parent: !uuid {root_component.uuid}
  extend:
    components:
      - name: {component["name"]}
"""
        decl.apply(model, io.StringIO(model_update))
        return model.search("LogicalComponent").by_name(component["name"])

    def add_part_to_component(self, model, parent_component, comp, new_comp):
        """Add a Part corresponding to the new LogicalComponent."""
        parent_component.owned_features.create("Part", name=comp["name"], type=new_comp)

    def create_logical_function(self, model, root_component, function):
        """Create a LogicalFunction under the specified root_component."""
        yaml.add_constructor("!uuid", lambda loader, node: loader.construct_scalar(node), Loader=yaml.SafeLoader)
        model_update = f"""
- parent: !uuid {root_component.uuid}
  extend:
    functions:
      - name: {function["name"]}
"""
        decl.apply(model, io.StringIO(model_update))

