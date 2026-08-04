# CadClaude FreeCAD Workbench
# GUI Initialization - runs when FreeCAD starts in GUI mode

import os
import sys
import FreeCAD
import FreeCADGui


_WORKBENCH_INSTANCE = None


class CadClaudeSettingsCommand:
    """Command to open CadClaude settings dialog"""

    def GetResources(self):
        return {
            'MenuText': 'Settings...',
            'ToolTip': 'Configure ElixiCAD FreeCAD workspace settings',
        }

    def Activated(self):
        from ui.SettingsPanel import show_settings_dialog

        def on_saved():
            if _WORKBENCH_INSTANCE and _WORKBENCH_INSTANCE.project_browser:
                _WORKBENCH_INSTANCE.project_browser.apply_settings()
            if _WORKBENCH_INSTANCE and _WORKBENCH_INSTANCE.chat_panel:
                _WORKBENCH_INSTANCE.chat_panel._apply_settings_from_config()

        show_settings_dialog(FreeCADGui.getMainWindow(), on_saved=on_saved)

    def IsActive(self):
        return True


# Register command
FreeCADGui.addCommand('CadClaude_Settings', CadClaudeSettingsCommand())


class CadClaudeWorkbench(FreeCADGui.Workbench):
    """CadClaude workbench - AI-assisted CAD modeling with Claude"""

    MenuText = "ElixiCAD"
    ToolTip = "Open and modify ElixiCAD projects in FreeCAD"

    PENDING_OPEN_FILE = os.path.expanduser("~/.cadclaude/pending_open_project")

    def __init__(self):
        global _WORKBENCH_INSTANCE
        _WORKBENCH_INSTANCE = self
        self.chat_panel = None
        self.project_browser = None
        self._workbench_dir = None
        self._current_project = None
        self._open_timer = None

    def _get_workbench_dir(self):
        """Find the workbench directory path"""
        if self._workbench_dir is not None:
            return self._workbench_dir

        # Search FreeCAD's mod paths — symlink now points directly to freecad/
        search_paths = [
            os.path.join(FreeCAD.getUserAppDataDir(), "Mod", "CadClaude"),
            os.path.join(FreeCAD.getResourceDir(), "Mod", "CadClaude"),
            os.path.expanduser("~/Library/Application Support/FreeCAD/Mod/CadClaude"),
            "/Users/user/dev/cadClaude/freecad",
        ]

        for path in search_paths:
            if os.path.exists(path):
                self._workbench_dir = path
                # Adding the workbench dir to sys.path gives access to:
                #   core/, ui/, shared/ (symlink → ../shared)
                # Do NOT add the repo root — that would shadow FreeCAD's own
                # `freecad` namespace package and break internal FreeCAD imports.
                if path not in sys.path:
                    sys.path.insert(0, path)
                return path

        # Fallback
        self._workbench_dir = "/Users/user/dev/cadClaude/freecad"
        return self._workbench_dir

    @property
    def Icon(self):
        # Icons live under resources/icons/ relative to the freecad/ workbench dir
        return os.path.join(self._get_workbench_dir(), "resources", "icons", "cadclaude.svg")

    def Initialize(self):
        """Called when the workbench is first activated"""
        self._get_workbench_dir()  # Ensure path is set up

        # Create menu. Developer reload remains registered but is hidden by default.
        menu_commands = ["CadClaude_Settings"]
        if os.environ.get("ELIXICAD_FREECAD_DEV_TOOLS") == "1":
            menu_commands.append("CadClaude_Reload")
        self.appendMenu("ElixiCAD", menu_commands)

        FreeCAD.Console.PrintMessage("CadClaude workbench loaded\n")

    def Activated(self):
        """Called when switching to this workbench"""
        FreeCAD.Console.PrintMessage("CadClaude workbench activated\n")
        self._setup_panels()
        self._start_open_timer()
        # Check immediately — handles the "Open in FreeCAD" launch case.
        # If no pending file, fall back to restoring the last project.
        if not self._check_pending_open():
            self._restore_last_project()

    def Deactivated(self):
        """Called when switching away from this workbench"""
        FreeCAD.Console.PrintMessage("CadClaude workbench deactivated\n")
        self._save_last_project()
        self._hide_panels()
        self._stop_open_timer()

    def _restore_last_project(self):
        """Restore the last opened project on workbench activation"""
        if self._current_project is not None:
            # Already have a project open
            return

        try:
            from shared.Settings import get_settings
            from shared.Project import Project

            settings = get_settings()
            last_path = settings.last_project_path

            if last_path and os.path.isdir(last_path) and Project.is_project(last_path):
                FreeCAD.Console.PrintMessage(f"Restoring last project: {last_path}\n")
                project = Project.load(last_path)
                self._current_project = project

                if self.project_browser:
                    self.project_browser.set_project(project)
                if self.chat_panel:
                    self.chat_panel.set_current_project(project)

                FreeCAD.Console.PrintMessage(f"Opened project: {project.name}\n")
        except Exception as e:
            FreeCAD.Console.PrintWarning(f"Could not restore last project: {e}\n")

    def _start_open_timer(self):
        """Poll ~/.cadclaude/pending_open_project every 2 s for remote open requests."""
        if self._open_timer is not None:
            return
        try:
            from PySide6.QtCore import QTimer
        except ImportError:
            try:
                from PySide2.QtCore import QTimer
            except ImportError:
                return  # No Qt available — skip

        self._open_timer = QTimer()
        self._open_timer.setInterval(2000)
        self._open_timer.timeout.connect(self._check_pending_open)
        self._open_timer.start()

    def _stop_open_timer(self):
        if self._open_timer is not None:
            self._open_timer.stop()
            self._open_timer = None

    def _check_pending_open(self):
        """Load project from pending open file written by elixicad server.
        Returns True if a pending open was found and handled, False otherwise."""
        pending = self.PENDING_OPEN_FILE
        if not os.path.exists(pending):
            return False
        try:
            with open(pending, "r") as f:
                project_path = f.read().strip()
            os.remove(pending)
        except Exception as e:
            FreeCAD.Console.PrintWarning(f"CadClaude: could not read pending open file: {e}\n")
            return False

        if not project_path:
            return False

        try:
            from core.Project import Project
        except ImportError:
            try:
                from shared.Project import Project
            except ImportError:
                FreeCAD.Console.PrintWarning("ElixiCAD: project module not available\n")
                return False

        if not Project.is_project(project_path):
            FreeCAD.Console.PrintWarning(f"ElixiCAD: pending open path is not an ElixiCAD project: {project_path}\n")
            return False

        FreeCAD.Console.PrintMessage(f"ElixiCAD: opening ElixiCAD project: {project_path}\n")
        try:
            project = Project.load(project_path)
            self._current_project = project
            if self.project_browser:
                self.project_browser.set_project(project)
            if self.chat_panel:
                self.chat_panel.set_current_project(project)
            FreeCAD.Console.PrintMessage(f"ElixiCAD: opened ElixiCAD project '{project.name}'\n")
            return True
        except Exception as e:
            FreeCAD.Console.PrintWarning(f"ElixiCAD: failed to open ElixiCAD project {project_path}: {e}\n")
            return False

    def _save_last_project(self):
        """Save the current project path for restoration on next launch"""
        try:
            from shared.Settings import get_settings

            settings = get_settings()
            if self._current_project:
                settings.last_project_path = self._current_project.root_path
        except Exception as e:
            FreeCAD.Console.PrintWarning(f"Could not save last project: {e}\n")

    def _setup_panels(self):
        """Initialize and show the UI panels"""
        try:
            from PySide6 import QtCore, QtWidgets
            LeftDockArea = QtCore.Qt.DockWidgetArea.LeftDockWidgetArea
            RightDockArea = QtCore.Qt.DockWidgetArea.RightDockWidgetArea
        except ImportError:
            try:
                from PySide2 import QtCore, QtWidgets
                LeftDockArea = QtCore.Qt.LeftDockWidgetArea
                RightDockArea = QtCore.Qt.RightDockWidgetArea
            except ImportError:
                from PySide import QtCore, QtGui as QtWidgets
                LeftDockArea = QtCore.Qt.LeftDockWidgetArea
                RightDockArea = QtCore.Qt.RightDockWidgetArea

        main_window = FreeCADGui.getMainWindow()

        # Setup Project Browser (left side)
        if self.project_browser is None:
            from ui.ProjectBrowserPanel import ProjectBrowserPanel
            self.project_browser = ProjectBrowserPanel()
            self._connect_project_browser_signals()

        main_window.addDockWidget(LeftDockArea, self.project_browser)
        self.project_browser.show()

        # Setup Chat Panel (right side)
        if self.chat_panel is None:
            from ui.ChatPanel import ChatPanel
            self.chat_panel = ChatPanel()
            self._connect_chat_panel_signals()

        main_window.addDockWidget(RightDockArea, self.chat_panel)
        self.chat_panel.show()

    def _connect_project_browser_signals(self):
        """Connect project browser signals to handlers"""
        if self.project_browser:
            self.project_browser.runRequested.connect(self._on_run_body)
            self.project_browser.scriptRunRequested.connect(self._on_run_script)
            self.project_browser.viewRequested.connect(self._on_view_file)
            self.project_browser.fileDoubleClicked.connect(self._on_file_double_clicked)
            self.project_browser.bodySelected.connect(self._on_body_selected)
            self.project_browser.regenerateRequested.connect(self._on_regenerate_body)
            self.project_browser.bodyDeleted.connect(self._on_body_deleted)
            self.project_browser.assembleRequested.connect(self._on_assemble_requested)
            self.project_browser.disaggregateRequested.connect(self._on_disaggregate_body)
            self.project_browser.prepareAssemblyRequested.connect(self._on_prepare_assembly)
            self.project_browser.detectConnectionsRequested.connect(self._on_detect_connections)
            self.project_browser.assembleSubBodiesRequested.connect(self._on_assemble_sub_bodies)
            self.project_browser.closeProjectRequested.connect(self._on_close_project)

            # Track project changes via property override
            original_set_project = self.project_browser.set_project
            workbench = self  # Capture reference for closure
            def tracked_set_project(project):
                original_set_project(project)
                workbench._current_project = project
                FreeCAD.Console.PrintMessage(f"Project set: {project.name if project else 'None'}\n")
                if workbench.chat_panel:
                    workbench.chat_panel.set_current_project(project)

                # Save as last project for auto-restore
                if project:
                    try:
                        from shared.Settings import get_settings
                        get_settings().last_project_path = project.root_path
                    except Exception:
                        pass  # Non-critical

                # Auto-select first body if available
                if project and project.bodies:
                    first_body = project.bodies[0]
                    FreeCAD.Console.PrintMessage(f"Project has {len(project.bodies)} components, first: {first_body.name}\n")

                    if workbench.chat_panel:
                        workbench.chat_panel.set_current_body(first_body)
                        FreeCAD.Console.PrintMessage(f"Auto-selected component: {first_body.name}\n")
                    else:
                        FreeCAD.Console.PrintWarning("Chat panel not available for auto-select\n")
                elif workbench.chat_panel:
                    workbench.chat_panel.set_current_body(None)
            self.project_browser.set_project = tracked_set_project

    def _connect_chat_panel_signals(self):
        """Connect chat panel signals to handlers"""
        if self.chat_panel:
            self.chat_panel.saveBodyRequested.connect(self._on_save_body_requested)
            self.chat_panel.updateBodyRequested.connect(self._on_update_body_requested)
            self.chat_panel.bodyCreated.connect(self._on_body_created)
            self.chat_panel.settingsSaved.connect(self._on_settings_saved)
            # Connect code generation signal if available
            if hasattr(self.chat_panel, 'claude_process') and self.chat_panel.claude_process:
                self.chat_panel.claude_process.codeGenerated.connect(self._on_code_generated)

    def _on_settings_saved(self):
        """Apply saved settings to workbench-owned panels."""
        if self.project_browser:
            self.project_browser.apply_settings()

    def _on_body_created(self):
        """Handle body creation - refresh project browser"""
        if self.project_browser:
            self.project_browser._refresh_tree()

    def _on_body_selected(self, body):
        """Handle body selection in browser - set as current for editing"""
        if self.chat_panel:
            self.chat_panel.set_current_body(body)
            FreeCAD.Console.PrintMessage(f"Selected component for editing: {body.name}\n")

    def _on_regenerate_body(self, body):
        """Handle request to regenerate a body from its description"""
        FreeCAD.Console.PrintMessage(f"Regenerating component: {body.name}\n")
        
        if not self.chat_panel:
            FreeCAD.Console.PrintError("Chat panel not available\n")
            return
        
        if not body.description:
            FreeCAD.Console.PrintError(f"Component '{body.name}' has no description\n")
            return
        
        # Send regeneration request to chat panel
        self.chat_panel.regenerate_body(body)
    
    def _on_body_deleted(self, body_name: str):
        """Handle body deletion - clear chatbot context"""
        FreeCAD.Console.PrintMessage(f"Component '{body_name}' was deleted from project\n")

        # Notify chat panel to clear context
        if self.chat_panel:
            self.chat_panel.on_body_deleted(body_name)

    def _on_close_project(self):
        """Handle Close Project - close all documents, clear chat history and context"""
        FreeCAD.Console.PrintMessage("Closing project...\n")

        # Close all open FreeCAD documents
        for doc_name in list(FreeCAD.listDocuments().keys()):
            try:
                FreeCAD.closeDocument(doc_name)
            except Exception as e:
                FreeCAD.Console.PrintWarning(f"Could not close document {doc_name}: {e}\n")

        # Clear chat panel history and context
        if self.chat_panel:
            self.chat_panel.clear_conversation()

        # Clear project reference
        self._current_project = None

        # Update project browser to show no project
        if self.project_browser:
            self.project_browser.set_project(None)

        FreeCAD.Console.PrintMessage("Project closed\n")

    def _on_assemble_requested(self, project):
        """Handle Assemble button — switch to Create mode and ask Claude to build an assembly"""
        if not self.chat_panel:
            FreeCAD.Console.PrintError("Chat panel not available for assembly\n")
            return

        # Ensure we are in Create mode so Claude generates code
        self.chat_panel._chat_mode = 'create'
        self.chat_panel._mode_toggle.setChecked(True)
        self.chat_panel._update_mode_ui()
        self.chat_panel._apply_mode_to_claude()

        # Mark this as an assembly generation so ChatPanel routes it to assemblies/
        assembly_name = "assembly"
        self.chat_panel._pending_assembly_name = assembly_name
        # Clear body name and body code context — don't inject previous body code into assembly request
        self.chat_panel._current_body_name = None
        if self.chat_panel.claude_process:
            self.chat_panel.claude_process.set_body_context(None)

        # Build prompt with ABSOLUTE paths so Claude never guesses wrong locations
        component_lines = []
        for b in project.bodies:
            if b.has_fcstd:
                component_lines.append(f"  - {b.name}: {b.fcstd_path}")
            elif b.has_script:
                component_lines.append(f"  - {b.name}: (no FCStd yet — skip it)")
        components_detail = "\n".join(component_lines) if component_lines else "  (no components with FCStd files)"

        assembly_prompt = (
            f"Create an assembly document that combines these FreeCAD components. "
            f"Use these EXACT absolute FCStd file paths:\n{components_detail}\n\n"
            f"IMPORTANT: Use this pattern — do NOT use App::Link:\n"
            f"1. Create doc with FreeCAD.newDocument('assembly')\n"
            f"2. For each component: load it with FreeCAD.openDocument(path), copy its shapes into the assembly doc using Part::Feature, then close the component doc\n"
            f"3. Position each shape with shape.translate(Vector(x, y, z)) before assigning to feature.Shape\n"
            f"4. Call doc.recompute() and fitAll() at the end\n"
            f"Arrange them sensibly (e.g. ball centered in front of goal, resting on ground)."
        )
        self.chat_panel.input_field.setPlainText(assembly_prompt)
        self.chat_panel._on_send_clicked()
        FreeCAD.Console.PrintMessage(f"Assembly prompt sent for {len(project.bodies)} components\n")

    def _on_assemble_sub_bodies(self, body):
        """Assemble sub-bodies of a single body into a finished assembly document"""
        import glob

        if not self.chat_panel:
            FreeCAD.Console.PrintError("Chat panel not available\n")
            return

        # Find all sub-body FCStd files (not the main body FCStd)
        main_fcstd = os.path.basename(body.fcstd_path)
        sub_fcstds = sorted([
            f for f in glob.glob(os.path.join(body.path, "*.FCStd"))
            if os.path.basename(f) != main_fcstd
        ])

        if not sub_fcstds:
            FreeCAD.Console.PrintError(f"No split component FCStd files found in {body.path}\n")
            return

        # Read placements.json if it exists to inform positioning
        placements_content = ""
        placements_path = os.path.join(body.path, "placements.json")
        if os.path.exists(placements_path):
            try:
                with open(placements_path, 'r') as f:
                    placements_content = f"\nPlacements (world-space positions for each split component):\n```json\n{f.read()}\n```\n"
            except Exception:
                pass

        # Read sub-body scripts to give Claude geometry/parameter context
        main_script = os.path.basename(body.script_path) if body.script_path else ""
        scripts_content = []
        for script_path in sorted(glob.glob(os.path.join(body.path, "*.py"))):
            script_name = os.path.basename(script_path)
            if script_name == main_script or script_name.endswith("_disaggregate.py"):
                continue
            try:
                with open(script_path, 'r', encoding='utf-8', errors='replace') as f:
                    scripts_content.append(f"--- {script_name} ---\n{f.read()}")
            except Exception:
                pass

        scripts_section = ""
        if scripts_content:
            scripts_section = (
                "\nSplit component scripts (use these to understand each part's geometry, "
                "dimensions, and natural orientation before placing it):\n"
                + "\n\n".join(scripts_content) + "\n"
            )

        # Build list of split component files
        sub_bodies_list = "\n".join([f"  - {os.path.basename(f)}: {f}" for f in sub_fcstds])

        # Determine assembly output path
        assembly_dir = os.path.join(body.path, "assembly")
        assembly_fcstd = os.path.join(assembly_dir, f"{body.name}_assembly.FCStd")

        # Switch to Create mode and route to assemblies folder
        self.chat_panel._chat_mode = 'create'
        self.chat_panel._mode_toggle.setChecked(True)
        self.chat_panel._update_mode_ui()
        self.chat_panel._apply_mode_to_claude()

        assembly_name = f"{body.name}_assembly"
        self.chat_panel._pending_assembly_name = assembly_name
        self.chat_panel._current_body_name = None
        if self.chat_panel.claude_process:
            self.chat_panel.claude_process.set_body_context(None)

        prompt = (
            f"Create an assembly document that combines these split components of '{body.name}' "
            f"into a single finished assembly showing all parts in their correct positions.\n\n"
            f"Split component FCStd files:\n{sub_bodies_list}\n"
            f"{placements_content}"
            f"{scripts_section}\n"
            f"IMPORTANT - Placement and rotation:\n"
            f"- Use FreeCAD.Placement(Vector(x,y,z), Rotation(axis, angle_deg)) for ALL parts\n"
            f"- The rotation in placements.json is [axis_x, axis_y, axis_z, angle_deg]\n"
            f"- WARNING: placements.json may have incorrect or missing rotations (angle=0) "
            f"even when a part needs to be rotated. Do NOT blindly trust zero-angle rotations.\n"
            f"- Instead, reason from the split component scripts and the target position:\n"
            f"  * Check each part's script to understand its natural geometry (which axis it extends along, its bounding dimensions)\n"
            f"  * Use the world-space position to infer the part's role (e.g. a wall at a high X position is likely a side wall that needs rotation)\n"
            f"  * If a part's natural long axis does not match the direction it needs to run in the assembly, add the appropriate rotation\n\n"
            f"Use this exact pattern (do NOT use App::Link):\n"
            f"1. Create doc with FreeCAD.newDocument('{body.name}_assembly')\n"
            f"2. os.makedirs('{assembly_dir}', exist_ok=True)\n"
            f"3. For each split component:\n"
            f"   a. Load with FreeCAD.openDocument(path)\n"
            f"   b. Get shape: shape = [o.Shape for o in part_doc.Objects if hasattr(o,'Shape')][-1].copy()\n"
            f"   c. Close split component doc\n"
            f"   d. Apply placement: shape.Placement = FreeCAD.Placement(Vector(x,y,z), Rotation(axis, angle_deg))\n"
            f"   e. feature = doc.addObject('Part::Feature', name); feature.Shape = shape\n"
            f"4. doc.recompute()\n"
            f"5. doc.saveAs('{assembly_fcstd}')\n"
            f"6. if FreeCAD.GuiUp: FreeCAD.Gui.ActiveDocument.ActiveView.fitAll()\n\n"
            f"The output FCStd must be saved to: {assembly_fcstd}"
        )

        self.chat_panel.input_field.setPlainText(prompt)
        self.chat_panel._on_send_clicked()
        FreeCAD.Console.PrintMessage(f"Split component assembly prompt sent for '{body.name}'\n")

    def _on_disaggregate_body(self, body):
        """Send a disaggregation prompt to Claude to split a body into sub-component scripts"""
        if not self.chat_panel:
            FreeCAD.Console.PrintError("Chat panel not available for disaggregation\n")
            return

        if not body.has_script:
            FreeCAD.Console.PrintError(f"Component '{body.name}' has no script to split\n")
            return

        try:
            with open(body.script_path, 'r') as f:
                script_content = f.read()
        except Exception as e:
            FreeCAD.Console.PrintError(f"Failed to read script for '{body.name}': {e}\n")
            return

        # Switch to Create mode so Claude generates code
        self.chat_panel._chat_mode = 'create'
        self.chat_panel._mode_toggle.setChecked(True)
        self.chat_panel._update_mode_ui()

        # Clear body context so previous code doesn't leak into the prompt
        self.chat_panel._current_body_name = None
        if self.chat_panel.claude_process:
            self.chat_panel.claude_process.set_body_context(None)

        output_dir = body.path  # e.g. .../bodies/goal/

        disaggregate_prompt = (
            f"Split this FreeCAD component script into individually manufacturable sub-components.\n\n"
            f"Component name: {body.name}\n"
            f"Output directory: {output_dir}\n\n"
            f"Current script:\n```python\n{script_content}\n```\n\n"
            f"Generate a single Python script that:\n"
            f"1. Identifies each distinct physical sub-component (e.g. individual pipe/tube lengths, plates, brackets)\n"
            f"2. For each sub-component:\n"
            f"   a. Build the geometry at its NATURAL ORIGIN — e.g. a vertical post starts at Vector(0,0,0), "
            f"a horizontal bar starts at Vector(0,0,0) pointing along X. "
            f"This means each piece is clean for manufacturing/drawing.\n"
            f"   b. Record the world-space placement it occupies in the original component as a Vector (x, y, z) offset.\n"
            f"   c. Create a new FreeCAD document, add the origin-based shape, save and close:\n"
            f"      doc = FreeCAD.newDocument('subname')\n"
            f"      feature = doc.addObject('Part::Feature', 'subname')\n"
            f"      feature.Shape = <origin-based shape>\n"
            f"      doc.recompute()\n"
            f"      doc.saveAs('{output_dir}/subname.FCStd')\n"
            f"      FreeCAD.closeDocument(doc.Name)\n"
            f"3. After saving all sub-components, write a placements.json file to '{output_dir}/placements.json':\n"
            f"   The JSON is a list of objects, one per sub-component:\n"
            f"   [\n"
            f"     {{\"name\": \"subname\", \"file\": \"{output_dir}/subname.FCStd\",\n"
            f"      \"position\": [x, y, z], \"rotation\": [ax, ay, az, angle_deg]}},\n"
            f"     ...\n"
            f"   ]\n"
            f"   - position is the Vector offset to move the part from origin to its place in the assembly\n"
            f"   - rotation axis+angle (use [0,0,1,0] if no rotation)\n"
            f"4. Names sub-components descriptively, e.g. '{body.name}_left_post', '{body.name}_crossbar'\n"
            f"5. Prints a summary of all sub-components and their placements at the end\n\n"
            f"IMPORTANT:\n"
            f"- Each sub-component must be a single piece that would be cut or fabricated separately\n"
            f"- Use Part (not PartDesign) for simple primitives — makeCylinder, makeBox, etc.\n"
            f"- The geometry in each FCStd is origin-based; the placements.json records where each piece lives\n"
            f"- When a sub-component appears multiple times (e.g. identical posts), create ONE FCStd for the "
            f"geometry but include MULTIPLE entries in placements.json — one per instance with its own position"
        )

        self.chat_panel.input_field.setPlainText(disaggregate_prompt)
        self.chat_panel._on_send_clicked()
        FreeCAD.Console.PrintMessage(f"Split component prompt sent for '{body.name}'\n")

    def _on_prepare_assembly(self, body, method: str, bolt_size=None):
        """Send assembly preparation prompt to Claude with sub-body FCStd files and placements"""
        import glob

        if not self.chat_panel:
            FreeCAD.Console.PrintError("Chat panel not available\n")
            return

        # Find all sub-body FCStd files (not the main body FCStd)
        main_fcstd = os.path.basename(body.fcstd_path)
        sub_fcstds = sorted([
            f for f in glob.glob(os.path.join(body.path, "*.FCStd"))
            if os.path.basename(f) != main_fcstd
        ])

        if not sub_fcstds:
            FreeCAD.Console.PrintError(f"No split component FCStd files found in {body.path}\n")
            return

        # Build list of split component files
        sub_bodies_list = "\n".join([f"  - {os.path.basename(f)}: {f}" for f in sub_fcstds])

        # Read placements.json if it exists
        placements_content = ""
        placements_path = os.path.join(body.path, "placements.json")
        if os.path.exists(placements_path):
            try:
                with open(placements_path, 'r') as f:
                    placements_content = f"\nPlacements (world-space positions):\n```json\n{f.read()}\n```\n"
            except Exception:
                pass

        # Read connections.json if it exists (generated by Detect Connections)
        connections_content = ""
        connections_path = os.path.join(body.path, "connections.json")
        if os.path.exists(connections_path):
            try:
                with open(connections_path, 'r') as f:
                    connections_content = (
                        f"\nDetected connections (use these to determine WHERE to apply modifications):\n"
                        f"```json\n{f.read()}\n```\n"
                    )
            except Exception:
                pass

        # Switch to Create mode
        self.chat_panel._chat_mode = 'create'
        self.chat_panel._mode_toggle.setChecked(True)
        self.chat_panel._update_mode_ui()

        # Clear body context
        self.chat_panel._current_body_name = None
        if self.chat_panel.claude_process:
            self.chat_panel.claude_process.set_body_context(None)

        # Build method-specific instructions
        if method == "weld":
            method_instructions = (
                "Apply weld preparation modifications:\n"
                "- For T-junctions (tube end meeting tube side): add cope cut to the end tube\n"
                "  cope_cutter = Part.makeCylinder(mating_tube_radius, length, contact_point, mating_axis)\n"
                "  modified = original.cut(cope_cutter)\n"
                "- For butt joints: add bevel prep (37.5 deg typical) using cone subtraction\n"
                "- Adjust lengths to account for weld fillets if needed"
            )
        elif method == "bolt":
            size = bolt_size or "M6"
            bolt_dims = {
                "M4":     (4.5,  8.5,  4.4),
                "M6":     (6.5,  11.0, 6.0),
                "M8":     (8.5,  14.5, 8.0),
                "M10":    (10.5, 17.5, 10.0),
                '1/4"-20': (6.9, 12.0, 6.35),
            }
            through, cbore, depth = bolt_dims.get(size, bolt_dims["M6"])
            method_instructions = (
                f"Apply {size} bolt hole modifications:\n"
                f"- Counterbored through-holes: {through}mm through-hole, {cbore}mm counterbore diameter, {depth}mm counterbore depth\n"
                f"  through_hole = Part.makeCylinder({through}/2, thickness, center, normal)\n"
                f"  counterbore = Part.makeCylinder({cbore}/2, {depth}, center, normal)\n"
                f"  modified = original.cut(through_hole).cut(counterbore)"
            )
        else:
            method_instructions = "Apply appropriate joining modifications based on the geometry."

        prompt = (
            f"Prepare these split components for {method}ed assembly.\n\n"
            f"Parent component: {body.name}\n"
            f"Output directory: {body.path}\n"
            f"{placements_content}"
            f"{connections_content}\n"
            f"Split component FCStd files:\n{sub_bodies_list}\n\n"
            f"{method_instructions}\n\n"
            f"Generate a single Python script that:\n"
            f"1. Opens each split component FCStd file using FreeCAD.openDocument(path)\n"
            f"2. Gets the shape from the document's objects\n"
            f"3. Uses the detected connections (if provided) to determine exactly WHERE to apply modifications\n"
            f"4. Applies the joining modifications based on connection geometry\n"
            f"5. Updates the shape in the document and saves (doc.save())\n"
            f"6. Closes each document after saving\n"
            f"7. Prints a summary of modifications made\n\n"
            f"If connections.json is provided, apply modifications at the specified contact points. "
            f"Otherwise, analyze the placements to infer where parts connect."
        )

        self.chat_panel.input_field.setPlainText(prompt)
        self.chat_panel._on_send_clicked()
        FreeCAD.Console.PrintMessage(f"Assembly prep prompt sent for {body.name} ({method})\n")

    def _on_detect_connections(self, body):
        """Send connection detection prompt to Claude to analyze sub-body geometry"""
        import glob

        if not self.chat_panel:
            FreeCAD.Console.PrintError("Chat panel not available\n")
            return

        # Find all sub-body FCStd files (not the main body FCStd)
        main_fcstd = os.path.basename(body.fcstd_path)
        sub_fcstds = sorted([
            f for f in glob.glob(os.path.join(body.path, "*.FCStd"))
            if os.path.basename(f) != main_fcstd
        ])

        if not sub_fcstds:
            FreeCAD.Console.PrintError(f"No split component FCStd files found in {body.path}\n")
            return

        # Build list of sub-body files
        sub_bodies_list = "\n".join([f"  - {os.path.basename(f)}: {f}" for f in sub_fcstds])

        # Read placements.json if it exists
        placements_content = ""
        placements_path = os.path.join(body.path, "placements.json")
        if os.path.exists(placements_path):
            try:
                with open(placements_path, 'r') as f:
                    placements_content = f"\nPlacements (world-space positions):\n```json\n{f.read()}\n```\n"
            except Exception:
                pass

        # Switch to Create mode
        self.chat_panel._chat_mode = 'create'
        self.chat_panel._mode_toggle.setChecked(True)
        self.chat_panel._update_mode_ui()

        # Clear body context
        self.chat_panel._current_body_name = None
        if self.chat_panel.claude_process:
            self.chat_panel.claude_process.set_body_context(None)

        output_path = os.path.join(body.path, "connections.json")

        prompt = (
            f"Detect connections between these split components and generate a connections.json file.\n\n"
            f"Parent component: {body.name}\n"
            f"Output file: {output_path}\n"
            f"{placements_content}\n"
            f"Split component FCStd files:\n{sub_bodies_list}\n\n"
            f"Generate a Python script that:\n"
            f"1. Opens each split component FCStd file\n"
            f"2. Applies the placement transforms from placements.json\n"
            f"3. For each pair of parts, uses shape_a.distToShape(shape_b) to check if they touch (distance < 1mm)\n"
            f"4. For touching parts, determines:\n"
            f"   - contact_point: the point where they meet\n"
            f"   - contact_type: 'tube_end_to_tube_side', 'tube_end_to_tube_end', 'face_to_face', etc.\n"
            f"   - part axes if applicable (for tubes)\n"
            f"5. Writes connections.json with format:\n"
            f"```json\n"
            f"[\n"
            f"  {{\n"
            f"    \"part_a\": \"goal_left_post\",\n"
            f"    \"part_b\": \"goal_crossbar\",\n"
            f"    \"contact_point\": [x, y, z],\n"
            f"    \"contact_type\": \"tube_end_to_tube_side\",\n"
            f"    \"joint_type\": \"T-junction\",\n"
            f"    \"part_a_axis\": [0, 0, 1],\n"
            f"    \"part_b_axis\": [1, 0, 0],\n"
            f"    \"modifications\": {{\n"
            f"      \"part_a\": \"none\",\n"
            f"      \"part_b\": \"cope_cut\"\n"
            f"    }}\n"
            f"  }}\n"
            f"]\n"
            f"```\n"
            f"6. Prints a summary of detected connections\n\n"
            f"Use shape.distToShape() to find contact points. For cylinders, determine axes from bounding box dimensions."
        )

        self.chat_panel.input_field.setPlainText(prompt)
        self.chat_panel._on_send_clicked()
        FreeCAD.Console.PrintMessage(f"Connection detection prompt sent for {body.name}\n")

    def _on_run_body(self, body):
        """Handle request to run a body's script"""
        FreeCAD.Console.PrintMessage(f"Running component: {body.name}\n")

        if not body.has_script:
            FreeCAD.Console.PrintError(f"Component {body.name} has no script\n")
            return

        # Read the script to determine if it's FreeCAD or CadQuery code
        try:
            with open(body.script_path, 'r') as f:
                code = f.read()
        except Exception as e:
            FreeCAD.Console.PrintError(f"Failed to read script: {e}\n")
            return

        # Detect code type - FreeCAD code imports FreeCAD, CadQuery imports cadquery
        is_freecad_code = 'import FreeCAD' in code or 'from FreeCAD' in code
        is_cadquery_code = 'import cadquery' in code or 'from cadquery' in code

        if is_freecad_code and not is_cadquery_code:
            # Use FreeCADExecutor for FreeCAD-native code (runs inside FreeCAD)
            from core.FreeCADExecutor import FreeCADExecutor
            executor = FreeCADExecutor()
            result = executor.execute_code(code, body.path, body.name)
            
            if result.success:
                body.mark_generated()
                FreeCAD.Console.PrintMessage(f"Component {body.name} executed successfully\n")
                # Refresh browser
                if self.project_browser:
                    self.project_browser._refresh_tree()
                # Auto-view the model
                if result.document_path and os.path.exists(result.document_path):
                    self._on_view_file(result.document_path)
            else:
                body.mark_error(result.error)
                FreeCAD.Console.PrintError(f"Component {body.name} failed: {result.error}\n")
        else:
            # Use ScriptRunner for CadQuery code (runs in subprocess with separate Python)
            from core.CodeExecutor import ScriptRunner
            runner = ScriptRunner(self._current_project)
            result = runner.run_body(body)

            if result.success:
                FreeCAD.Console.PrintMessage(f"Component {body.name} executed successfully\n")
                # Refresh browser to show updated status
                if self.project_browser:
                    self.project_browser._refresh_tree()
                # Auto-view if files were generated
                if result.generated_files:
                    self._on_view_file(result.generated_files[0])
            else:
                FreeCAD.Console.PrintError(f"Component {body.name} failed: {result.error}\n")

    def _on_run_script(self, script_path):
        """Handle request to run a Python script file"""
        FreeCAD.Console.PrintMessage(f"Running script: {script_path}\n")

        if not os.path.exists(script_path):
            FreeCAD.Console.PrintError(f"Script not found: {script_path}\n")
            return

        from core.FreeCADExecutor import FreeCADExecutor
        executor = FreeCADExecutor()

        # Determine output directory (same as script location)
        output_dir = os.path.dirname(script_path)
        body_name = os.path.splitext(os.path.basename(script_path))[0]

        # Read and execute the script
        try:
            with open(script_path, 'r') as f:
                code = f.read()

            result = executor.execute_code(code, output_dir, body_name)

            if result.success:
                FreeCAD.Console.PrintMessage(f"Script executed successfully: {body_name}\n")
                # Refresh browser to show any new/updated files
                if self.project_browser:
                    self.project_browser._refresh_tree()
                # Auto-view the model if FCStd was created
                if result.document_path and os.path.exists(result.document_path):
                    self._on_view_file(result.document_path)
            else:
                FreeCAD.Console.PrintError(f"Script execution failed: {result.error}\n")
        except Exception as e:
            FreeCAD.Console.PrintError(f"Error running script: {e}\n")

    def _on_view_file(self, file_path):
        """Handle request to view a file in FreeCAD viewport"""
        FreeCAD.Console.PrintMessage(f"Viewing file: {file_path}\n")

        from core.ViewportManager import get_viewport_manager
        viewport = get_viewport_manager()
        viewport.import_file(file_path)

    def _on_file_double_clicked(self, file_path):
        """Handle double-click on a file"""
        if file_path.endswith('.py'):
            # Open in external editor
            import subprocess
            if sys.platform == "darwin":
                subprocess.run(["open", file_path])
            elif sys.platform == "win32":
                os.startfile(file_path)
            else:
                subprocess.run(["xdg-open", file_path])
        elif file_path.endswith(('.step', '.stp', '.stl', '.FCStd')):
            self._on_view_file(file_path)

    def _on_code_generated(self, code):
        """Handle code generated by Claude"""
        FreeCAD.Console.PrintMessage("Code generated by Claude\n")

    def _on_update_body_requested(self, code: str):
        """Handle request to update current body with new code.
        
        NOTE: This is called AFTER ChatPanel has already executed the code,
        so we only need to save the script - no need to re-execute.
        """
        if not self.chat_panel or not self.chat_panel._current_body:
            FreeCAD.Console.PrintError("No current component to update\n")
            return

        body = self.chat_panel._current_body

        try:
            from shared.CodeExtractor import CodeExtractor

            # Prepare the updated code
            extractor = CodeExtractor()
            prepared_code = extractor.prepare_script_for_body(
                code, body.name, body.path
            )
            body.set_script_content(prepared_code)

            FreeCAD.Console.PrintMessage(f"Updated component script: {body.name}\n")

            # Update Claude's context with the new code
            if self.chat_panel.claude_process:
                self.chat_panel.claude_process.set_body_context(prepared_code, body.name)

            # Refresh browser
            if self.project_browser:
                self.project_browser._refresh_tree()

            # NOTE: Do NOT re-run the body here - ChatPanel already executed it!
            # The _on_run_body call was causing double-execution

        except Exception as e:
            FreeCAD.Console.PrintError(f"Failed to update component: {e}\n")

    def _on_save_body_requested(self, code: str, name: str):
        """Handle request to save code as a body"""
        if not self._current_project:
            # Need to prompt user to create/open a project first
            try:
                from PySide6 import QtWidgets
            except ImportError:
                try:
                    from PySide2 import QtWidgets
                except ImportError:
                    from PySide import QtGui as QtWidgets

            result = QtWidgets.QMessageBox.question(
                self.chat_panel,
                "No Project Open",
                "You need to open or create a project first.\nWould you like to create a new project?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
                if hasattr(QtWidgets.QMessageBox, 'StandardButton')
                else QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )

            yes_btn = (QtWidgets.QMessageBox.StandardButton.Yes
                      if hasattr(QtWidgets.QMessageBox, 'StandardButton')
                      else QtWidgets.QMessageBox.Yes)

            if result == yes_btn:
                self.project_browser._on_new_project()
                self._current_project = self.project_browser.project

            if not self._current_project:
                return

        try:
            from shared.Body import Body
            from shared.CodeExtractor import CodeExtractor

            # Prepare the code for the body
            extractor = CodeExtractor()
            body = Body.create(name, self._current_project)

            # Prepare script with proper paths
            prepared_code = extractor.prepare_script_for_body(
                code, name, body.path
            )
            body.set_script_content(prepared_code)

            # Set this as the current body for future updates
            if self.chat_panel:
                self.chat_panel.set_current_body(body)
                # Explicitly set Claude context with the prepared code
                if self.chat_panel.claude_process:
                    self.chat_panel.claude_process.set_body_context(prepared_code, name)
                    FreeCAD.Console.PrintMessage(f"Set Claude context for component: {name}\n")

            # Refresh browser
            if self.project_browser:
                self.project_browser._refresh_tree()

            FreeCAD.Console.PrintMessage(f"Created component: {name}\n")

            # Run the body
            self._on_run_body(body)

        except Exception as e:
            FreeCAD.Console.PrintError(f"Failed to create component: {e}\n")

    def _hide_panels(self):
        """Hide UI panels when workbench is deactivated"""
        if self.chat_panel is not None:
            self.chat_panel.hide()
        if self.project_browser is not None:
            self.project_browser.hide()

    def GetClassName(self):
        return "Gui::PythonWorkbench"


class CadClaudeReloadCommand:
    """Command to hot-reload CadClaude modules during development"""
    
    def GetResources(self):
        return {
            'MenuText': 'Reload Modules (Dev)',
            'ToolTip': 'Hot-reload all CadClaude modules without restarting FreeCAD',
        }
    
    def Activated(self):
        import importlib
        
        # List of modules to reload in dependency order
        modules_to_reload = [
            'core.config',
            'core.prompts',
            'core.freecad_prompts',
            'core.CodeExtractor',
            'core.GeometryValidator',
            'core.CodeExecutor',
            'core.FreeCADExecutor',
            'core.ViewportManager',
            'core.ClaudeProcess',
            'core.Component',
            'core.Project',
            'ui.ChatMessage',
            'ui.ChatPanel',
            'ui.ProjectBrowserPanel',
        ]
        
        reloaded = []
        failed = []
        
        for module_name in modules_to_reload:
            try:
                if module_name in sys.modules:
                    module = sys.modules[module_name]
                    importlib.reload(module)
                    reloaded.append(module_name)
            except Exception as e:
                failed.append(f"{module_name}: {e}")
        
        # Report results
        if reloaded:
            FreeCAD.Console.PrintMessage(f"✓ Reloaded {len(reloaded)} modules: {', '.join(reloaded)}\n")
        if failed:
            FreeCAD.Console.PrintWarning(f"⚠ Failed to reload:\n")
            for f in failed:
                FreeCAD.Console.PrintWarning(f"  {f}\n")
        
        if not failed:
            FreeCAD.Console.PrintMessage("🔄 CadClaude hot-reload complete!\n")
    
    def IsActive(self):
        return True


# Register commands
FreeCADGui.addCommand('CadClaude_Reload', CadClaudeReloadCommand())

# Register the workbench
FreeCADGui.addWorkbench(CadClaudeWorkbench())


def _check_pending_open_at_startup():
    """
    Called once after FreeCAD finishes GUI initialisation.
    If ~/.cadclaude/pending_open_project exists, switch to the CadClaude
    workbench — its Activated() handler will then pick up the pending file
    via the polling timer and load the project.
    """
    pending = os.path.expanduser("~/.cadclaude/pending_open_project")
    if not os.path.exists(pending):
        return

    FreeCAD.Console.PrintMessage("ElixiCAD: pending open detected — activating workbench\n")
    try:
        FreeCADGui.activateWorkbench("CadClaudeWorkbench")
    except Exception as e:
        FreeCAD.Console.PrintWarning(f"ElixiCAD: could not activate workbench at startup: {e}\n")


try:
    from PySide6.QtCore import QTimer as _QTimer
except ImportError:
    try:
        from PySide2.QtCore import QTimer as _QTimer
    except ImportError:
        _QTimer = None

if _QTimer is not None:
    _startup_timer = _QTimer()
    _startup_timer.setSingleShot(True)
    _startup_timer.timeout.connect(_check_pending_open_at_startup)
    # 1 s delay — enough for FreeCAD's GUI to finish initialising
    _startup_timer.start(1000)
