"""libdnf5 resolve/serialize only. No transaction runner or downloader call."""
from pathlib import Path
from core import require, ROOTS, validate_actions


def solve(work, installed, modules=None):
    if modules is None:
        import libdnf5.base as base_module
        import libdnf5.transaction as transaction_module
    else:
        base_module, transaction_module = modules
    work = Path(work)
    base = base_module.Base()
    config = base.get_config()
    # Set every host-relative path explicitly before setup; never load host config.
    values = {
        "installroot": str(work / "solver-root"),
        "config_file_path": str(work / "config/dnf.conf"),
        "plugins": False, "pluginpath": str(work / "config/empty-plugins"),
        "plugin_conf_dir": [str(work / "config/empty-plugins")],
        "varsdir": [str(work / "config/empty-vars")],
        "reposdir": [str(work / "config/repos")],
        "cachedir": str(work / "cache"), "system_cachedir": str(work / "cache"),
        "logdir": str(work / "dnf-logs"), "persistdir": "/audit/persist",
        "system_state_dir": "/usr/lib/sysimage/libdnf5",
        "use_host_config": False,
        "transaction_history_dir": "/audit/history",
        "optional_metadata_types": ["filelists"], "zchunk": False,
        "install_weak_deps": True, "clean_requirements_on_remove": False,
        "skip_if_unavailable": False, "best": True,
        "pkg_gpgcheck": True, "retries": 1, "max_parallel_downloads": 1,
    }
    for name, value in values.items():
        getattr(config, "get_" + name + "_option")().set(value)
    base.get_vars().set("releasever", "44")
    base.get_vars().set("basearch", "x86_64")
    base.setup()
    # Runtime-priority absolute config paths survive setup; three deliberately
    # logical paths are always appended to installroot by this pinned API.
    for name, expected in values.items():
        actual = getattr(config, "get_" + name + "_option")().get_value()
        if isinstance(expected, list):
            actual = list(actual)
        require(actual == expected, "post-setup solver option changed:" + name)
    require(base.get_vars().get_value("releasever") == "44" and
        base.get_vars().get_value("basearch") == "x86_64", "post-setup solver vars changed")
    require(not list(base.get_plugins_info()), "libdnf5 plugins loaded")
    sack = base.get_repo_sack()
    sack.create_repos_from_system_configuration()
    # Every configured repo is a preverified file:/// mirror, with no metalink,
    # mirrorlist or payload request. Container is network-disabled for this phase.
    sack.update_and_load_enabled_repos(True)
    goal = base_module.Goal(base)
    goal.set_allow_erasing(True)
    goal.add_rpm_remove("ffmpeg-free")
    for name, evr in ROOTS.items():
        settings = base_module.GoalJobSettings()
        settings.set_from_repo_ids(["updates" if name == "gstreamer1-plugin-libav"
            else "rpmfusion-free-updates"])
        goal.add_rpm_install(name + "-" + evr + ".x86_64", settings)
    transaction = goal.resolve()
    require(int(transaction.get_problems()) == 0, "dependency solve failed")
    rows = []
    for item in transaction.get_transaction_packages():
        package = item.get_package()
        action = transaction_module.transaction_item_action_to_string(item.get_action())
        rows.append({"name": package.get_name(),
            "evr": (package.get_epoch() or "0") + ":" + package.get_version() + "-" + package.get_release(),
            "arch": package.get_arch(), "repo": package.get_repo_id(), "action": action,
            "download_bytes": int(package.get_download_size()),
            "installed_bytes": int(package.get_install_size()), "location": package.get_location()})
    inbound = validate_actions(rows, installed)
    # serialize() is explicitly not replayed/downloaded/run.
    serialized = transaction.serialize()
    return rows, inbound, serialized, values
