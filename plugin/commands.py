import importlib
import os
import sublime
import sublime_plugin

from types import ModuleType
from typing import Any, Dict, List, Optional, Tuple, cast

from lsp_utils.server_npm_resource import ServerNpmResource, get_server_npm_resource_for_package

from .functions import console_msg, error_box, info_box, get_command_name
from .patcher import AlreadyPatchedException, Patcher, restore_directory, json_dumps


def st_command_precheck() -> Optional[Tuple[ModuleType, ServerNpmResource]]:
    try:
        plugin_module = importlib.import_module("LSP-intelephense.plugin")
        lsp_plugin = plugin_module.LspIntelephensePlugin  # type: ignore
    except (ImportError, AttributeError):
        error_box("LSP-intelephense is not installed...")
        return None

    server_resource = get_server_npm_resource_for_package(
        lsp_plugin.package_name,
        lsp_plugin.server_directory,
        lsp_plugin.server_binary_path,
        lsp_plugin.package_storage(),
        lsp_plugin.minimum_node_version(),
    )  # type: Optional[ServerNpmResource]

    if not server_resource:
        error_box("LSP-intelephense does not seem to be usable...")
        return None

    if not os.path.isfile(server_resource.binary_path):
        error_box(
            # ...
            "The intelephense server has not been installed yet... "
            "Open a PHP project to install it and then retry."
        )
        return None

    return (plugin_module, server_resource)


class PatcherLspIntelephensePatchCommand(sublime_plugin.ApplicationCommand):
    def run(self) -> None:
        _, server_resource = st_command_precheck() or (None, None)

        if not server_resource:
            return None

        binary_path = server_resource.binary_path

        is_already_patched = False
        is_success = False

        try:
            is_success, occurrences = Patcher.patch_file(binary_path)

            if is_success and occurrences > 0:
                info_box(
                    '"{}" is patched with {} occurrences!\n\n'
                    "Restart ST to use the premium version.".format(binary_path, occurrences)
                )
            else:
                error_box("Unfortunately, somehow the patching failed.")
        except AlreadyPatchedException:
            is_already_patched = True
            is_success = True

        if not is_success:
            return None

        patch_info = Patcher.extract_patch_info(binary_path)

        if is_already_patched:
            msgs = ['"{bin}" had been already patched...\n\n']

            if Patcher.VERSION > patch_info["version"]:
                msgs.append("But the current patcher ({v_new}) is newer than the patching one ({v_old}).")

            info_box("".join(msgs).strip().format(bin=binary_path, v_old=patch_info["version"], v_new=Patcher.VERSION))

        console_msg("Patch info: {}".format(json_dumps(patch_info)))


class PatcherLspIntelephenseUnpatchCommand(sublime_plugin.ApplicationCommand):
    def run(self) -> None:
        _, server_resource = st_command_precheck() or (None, None)

        if not server_resource:
            return None

        binary_path = server_resource.binary_path

        restored_files = restore_directory(os.path.dirname(binary_path))

        if restored_files:
            restored_files_len = len(restored_files)

            for idx, file in enumerate(restored_files):
                console_msg("{}/{} file restored: {}".format(idx + 1, restored_files_len, file))

            info_box("{} files have been restored.".format(restored_files_len))
        else:
            error_box("No file has been restored...")


class PatcherLspIntelephenseRepatchCommand(sublime_plugin.ApplicationCommand):
    def run(self) -> None:
        _, server_resource = st_command_precheck() or (None, None)

        if not server_resource:
            return None

        sublime.run_command(get_command_name(PatcherLspIntelephenseUnpatchCommand))
        sublime.run_command(get_command_name(PatcherLspIntelephensePatchCommand))


class PatcherLspIntelephenseOpenServerBinaryDirCommand(sublime_plugin.WindowCommand):
    def run(self) -> None:
        _, server_resource = st_command_precheck() or (None, None)

        if not server_resource:
            return None

        binary_path = server_resource.binary_path

        self.window.run_command("open_dir", {"dir": os.path.dirname(binary_path)})


class PatcherLspIntelephenseShowMenuCommand(sublime_plugin.WindowCommand):
    menu_items = [
        ("Patch Intelephense", PatcherLspIntelephensePatchCommand, {}),
        ("Un-patch Intelephense", PatcherLspIntelephenseUnpatchCommand, {}),
        ("Re-patch Intelephense", PatcherLspIntelephenseRepatchCommand, {}),
        ("Open Server Binary Directory", PatcherLspIntelephenseOpenServerBinaryDirCommand, {}),
    ]  # type: List[Tuple[str, type, Dict[str, Any]]]

    def run(self) -> None:
        titles, cmd_classes, cmd_args = cast(
            # make stupid type deduction tool happy
            Tuple[Tuple[str, ...], Tuple[type, ...], Tuple[Dict[str, Any], ...]],
            zip(*self.menu_items),
        )

        def on_select(idx: int) -> None:
            if idx < 0:
                return None

            self.window.run_command(get_command_name(cmd_classes[idx]), cmd_args[idx])

        self.window.show_quick_panel(titles, on_select=on_select)
