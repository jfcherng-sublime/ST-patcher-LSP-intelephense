from .patcher import AlreadyPatchedException
from .patcher import json_dumps
from .patcher import Patcher
from .patcher import PatcherUnsupportedException
from .patcher import restore_directory
from .plugin_message import console_msg
from .plugin_message import error_box
from .plugin_message import info_box
from .utils import get_command_name
from lsp_utils import ServerNpmResource
from types import ModuleType
from typing import Any, Callable, Dict, List, Tuple, cast
import importlib
import os
import sublime
import sublime_plugin


def restart_intelephense_server() -> None:
    view = sublime.active_window().active_view()
    if view:
        view.run_command("lsp_restart_server", {"config_name": "LSP-intelephense"})


def st_command_run_precheck(func: Callable) -> Callable:
    def wrap(self: sublime_plugin.Command, *args, **kwargs) -> None:
        def checker() -> Tuple[ModuleType, ServerNpmResource]:
            try:
                plugin_module = importlib.import_module("LSP-intelephense.plugin")
                lsp_plugin = plugin_module.LspIntelephensePlugin  # type: ignore
            except (ImportError, AttributeError):
                raise RuntimeError("LSP-intelephense is not installed...")

            server_resource = ServerNpmResource.create(
                {
                    "package_name": lsp_plugin.package_name,
                    "server_directory": lsp_plugin.server_directory,
                    "server_binary_path": lsp_plugin.server_binary_path,
                    "package_storage": lsp_plugin.package_storage(),
                    "minimum_node_version": lsp_plugin.minimum_node_version(),
                    "storage_path": lsp_plugin.storage_path(),
                }
            )

            if not server_resource:
                raise RuntimeError("LSP-intelephense does not seem to be usable...")

            if not os.path.isfile(server_resource.binary_path):
                raise RuntimeError(
                    "The intelephense server has not been installed yet... "
                    + "Open a PHP project to install it and then retry."
                )

            return (plugin_module, server_resource)

        try:
            _, server_resource = checker()
        except Exception as e:
            return error_box("[{_}] {}", e)

        return func(self, server_resource, *args, **kwargs)

    return wrap


class PatcherLspIntelephensePatchCommand(sublime_plugin.ApplicationCommand):
    @st_command_run_precheck
    def run(
        self,
        server_resource: ServerNpmResource,
        allow_unsupported: bool = False,
        is_direct: bool = True,
    ) -> None:
        binary_path = server_resource.binary_path

        is_already_patched = False
        is_success = False

        try:
            is_success, occurrences = Patcher.patch_file(binary_path, allow_unsupported)

            if is_success and occurrences > 0:
                info_box('[{_}] "{}" is patched with {} occurrences!', binary_path, occurrences)
            else:
                error_box("[{_}] Unfortunately, somehow the patching failed.")
        except AlreadyPatchedException:
            is_already_patched = True
            is_success = True
        except PatcherUnsupportedException as e:
            is_success = False
            error_box("[{_}] {}", e)

        if not is_success:
            return

        patch_info = Patcher.extract_patch_info(binary_path)

        if is_already_patched:
            msg = '[{_}] "{bin}" had been already patched...'

            if Patcher.VERSION > patch_info["version"]:
                msg += "\n\nBut the current patcher ({v_new}) is newer than the patching one ({v_old})."

            info_box(msg, bin=binary_path, v_old=patch_info["version"], v_new=Patcher.VERSION)

        if is_direct:
            restart_intelephense_server()

        console_msg("[{_}] Patch info: {}", json_dumps(patch_info))


class PatcherLspIntelephenseUnpatchCommand(sublime_plugin.ApplicationCommand):
    @st_command_run_precheck
    def run(
        self,
        server_resource: ServerNpmResource,
        is_direct: bool = True,
    ) -> None:
        binary_path = server_resource.binary_path

        restored_files = restore_directory(os.path.dirname(binary_path))

        if not restored_files:
            return error_box("[{_}] No file has been restored...")

        restored_files_len = len(restored_files)

        for idx, file in enumerate(restored_files):
            console_msg("[{_}] {}/{} file restored: {}", idx + 1, restored_files_len, file)

        if is_direct:
            restart_intelephense_server()

        info_box("[{_}] {} files have been restored.", restored_files_len)


class PatcherLspIntelephenseRepatchCommand(sublime_plugin.ApplicationCommand):
    @st_command_run_precheck
    def run(self, server_resource: ServerNpmResource) -> None:
        sublime.run_command(get_command_name(PatcherLspIntelephenseUnpatchCommand), {"is_direct": False})
        sublime.run_command(get_command_name(PatcherLspIntelephensePatchCommand), {"is_direct": False})
        restart_intelephense_server()


class PatcherLspIntelephenseOpenServerBinaryDirCommand(sublime_plugin.WindowCommand):
    @st_command_run_precheck
    def run(self, server_resource: ServerNpmResource) -> None:
        self.window.run_command("open_dir", {"dir": os.path.dirname(server_resource.binary_path)})


class PatcherLspIntelephenseShowMenuCommand(sublime_plugin.WindowCommand):
    menu_items = [
        # title, cmd_class, cmd_arg
        ("Patch Intelephense", PatcherLspIntelephensePatchCommand, {}),
        ("Patch Intelephense (Allow Unsupported)", PatcherLspIntelephensePatchCommand, {"allow_unsupported": True}),
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
                return

            self.window.run_command(get_command_name(cmd_classes[idx]), cmd_args[idx])

        self.window.show_quick_panel(titles, on_select=on_select)
