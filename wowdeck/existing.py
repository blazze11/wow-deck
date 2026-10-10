"""Import and register an existing Battle.net/World of Warcraft installation."""
from __future__ import annotations
import json, os
from . import deck, files, steam, ui

CONFIG = os.path.join(files.USER_DATA, 'existing-install.json')


def load_config() -> dict:
    try:
        data = json.load(open(CONFIG, encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(data: dict) -> None:
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    tmp = CONFIG + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, CONFIG)


def select_proton(root: str, current: str | None = None) -> str | None:
    tools = deck.available_proton_tools(root)
    if not tools:
        ui.error('No installed Proton version was found. Install Proton or GE-Proton through Steam first.')
        return None
    items = [(name, f'{version}  ({name})' + ('  [current]' if name == current else ''))
             for name, (version, _path) in sorted(tools.items(), key=lambda x: (x[0] != current, x[0].lower()))]
    return ui.menu('Choose the Proton version for Battle.net / WoW', items)


def register(root: str, steam_edit: bool = True, log=print) -> bool:
    """Ask for existing paths and create/reuse a Steam shortcut. Returns False on cancel."""
    bnet = ui.choose_file('Select the existing Battle.net.exe')
    if not bnet:
        return False
    bnet = os.path.abspath(os.path.expanduser(bnet))
    if os.path.basename(bnet).lower() != 'battle.net.exe' or not os.path.isfile(bnet):
        ui.error('Please select the installed Battle.net.exe, not the installer.')
        return False
    compat = ui.choose_directory('Select the Proton prefix / compatdata directory (the directory containing pfx)')
    if not compat:
        return False
    compat = os.path.abspath(os.path.expanduser(compat))
    if not os.path.isdir(os.path.join(compat, 'pfx')):
        ui.error('The selected prefix must contain a pfx/ directory. Select the compatdata directory, not pfx itself.')
        return False
    wow = ui.choose_directory('Select the existing World of Warcraft directory (containing _retail_ or _classic_)')
    if not wow:
        return False
    wow = os.path.abspath(os.path.expanduser(wow))
    wtf_dirs = deck.wow_wtf_dirs_for_install(wow)
    if not wtf_dirs:
        ui.error('No installed WoW flavour executable was found in that directory. Choose the parent directory containing _retail_, _classic_, etc.')
        return False
    tools = deck.available_proton_tools(root)
    if not tools:
        ui.error('No installed Proton version was found. Install Proton or GE-Proton through Steam first.')
        return False
    current = load_config().get('proton')
    tool = select_proton(root, current)
    if not tool:
        return False
    uds = steam.userdata_dirs(root)
    if not uds:
        ui.error('No Steam user profile found; log in to Steam once first.')
        return False
    # Reuse an existing Battle.net shortcut when it points at this executable; otherwise add one.
    sc = next((s for s in steam.list_shortcuts(root)
               if 'battle.net' in (s.name + s.exe).lower() and os.path.realpath(s.exe.strip('"')) == os.path.realpath(bnet)), None)
    if sc is None:
        if steam.steam_running():
            if not steam_edit or not steam.steam_shutdown():
                ui.error('Steam must be closed to add the shortcut. Close Steam and run setup again.')
                return False
        import zlib
        appid = (zlib.crc32(('wow-deck:existing:' + os.path.realpath(bnet)).encode()) | 0x80000000) & 0xFFFFFFFF
        # Prefix override is intentionally before the existing wrapper and %command%; Proton then
        # uses the selected prefix instead of creating a new, empty compatdata directory.
        wrapper = files.WRAPPER + ' ' if os.access(files.WRAPPER, os.X_OK) else ''
        options = f'STEAM_COMPAT_DATA_PATH="{compat}" {wrapper}%command%'
        sc = steam.add_shortcut(uds[0], 'Battle.net (existing installation)', bnet, os.path.dirname(bnet),
                                options, appid=appid, icon=steam.shortcut_icon_path())
        steam.set_shortcut_art(uds[0], appid, log)
        log(f'  created shortcut for existing Battle.net ({appid})')
    else:
        # Existing shortcuts retain their existing launch options; set the selected prefix explicitly.
        if steam.steam_running():
            if not steam_edit or not steam.steam_shutdown():
                ui.error('Steam must be closed to edit the shortcut. Close Steam and run setup again.')
                return False
        wrapper = files.WRAPPER + ' ' if os.access(files.WRAPPER, os.X_OK) else ''
        options = f'STEAM_COMPAT_DATA_PATH="{compat}" {wrapper}%command%'
        steam.set_launch_options(sc, options)
        sc.launch_options = options
        log(f'  updated shortcut "{sc.name}"')
    steam.set_compat_tool(root, sc.appid, tool)
    save_config({'battlenet_exe': bnet, 'compat_data': compat, 'wow_dir': wow, 'proton': tool, 'appid': sc.appid})
    log(f'  selected Proton: {tool}; prefix: {compat}; WoW: {wow}')
    # Keep Steam available even if the checklist has nothing else to install.
    if not steam.steam_running():
        steam.steam_launch()
    return True
