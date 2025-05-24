import os
import json
import logging
import platform
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

class ZenSyncConfig:
    """Configuration management for Zen sync operations"""
    
    def __init__(self, config_file: str = "zen_sync_config.json"):
        self.config_file = config_file
        self.config = self.load_config()
    
    def load_config(self) -> Dict:
        """Load configuration from file or create default"""
        default_config = {
            "aws": {
                "region": "us-east-1",
                "bucket": "",
                "prefix": "zen-profiles/",
                "endpoint_url": "",
                "disable_metadata": False,
                "signature_version": "s3v4",
                "access_key_id": "",
                "secret_access_key": "",
                "profile": ""
            },
            "sync": {
                "zen_roaming_path": "",
                "zen_local_path": "",
                "sync_cache_data": False,
                "exclude_patterns": [
                    "*.lock", "*.lck", "*-wal", "*-shm", "*-journal",
                    "parent.lock", "cookies.sqlite*", "webappsstore.sqlite*",
                    "storage/temporary/*", "storage/default/*/ls/*", "storage/permanent/*/ls/*",
                    "cache2/*", "jumpListCache/*", "offlineCache/*", "thumbnails/*",
                    "crashes/*", "minidumps/*", "shader-cache/*", "startupCache/*",
                    "safebrowsing/*", "logs/*", "sessionstore-backups/previous.jsonlz4",
                    "sessionstore-backups/upgrade.jsonlz4-*",
                    "Profile Groups/*.sqlite-shm", "Profile Groups/*.sqlite-wal"
                ],
                "include_important": [
                    "*.ini", "prefs.js", "user.js", "userChrome.css", "userContent.css",
                    "bookmarks.html", "places.sqlite", "favicons.sqlite", "key4.db",
                    "cert9.db", "extensions.json", "extension-settings.json",
                    "extension-preferences.json", "search.json.mozlz4", "handlers.json",
                    "containers.json", "zen-*.json", "zen-*.css", "chrome/**/*",
                    "profiles.ini", "installs.ini", "Profile Groups/*.sqlite",
                    "zen-keyboard-shortcuts.json", "zen-themes.json", "sessionstore.jsonlz4",
                    "sessionCheckpoints.json", "logins.json", "compatibility.ini"
                ]
            }
        }
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)

                # Merge with defaults for missing keys
                for key in default_config:
                    if key not in config:
                        config[key] = default_config[key]
                    elif isinstance(default_config[key], dict):
                        for subkey in default_config[key]:
                            if subkey not in config[key]:
                                config[key][subkey] = default_config[key][subkey]
                return config
            except Exception as e:
                logger.warning(f"Error loading config file: {e}. Using defaults.")
        
        return default_config
    
    def auto_detect_zen_paths(self) -> Dict[str, str]:
        """Auto-detect Zen browser installation paths"""
        system = platform.system()
        paths = {"roaming": "", "local": ""}
        
        if system == "Windows":
            roaming = os.path.expandvars(r"%APPDATA%\zen")
            local = os.path.expandvars(r"%LOCALAPPDATA%\zen")
        elif system == "Darwin":
            home = os.path.expanduser("~")
            roaming = os.path.join(home, "Library", "Application Support", "zen")
            local = os.path.join(home, "Library", "Caches", "zen")
        else:
            home = os.path.expanduser("~")
            roaming = os.path.join(home, ".zen")
            local = os.path.join(home, ".cache", "zen")
        
        if os.path.exists(roaming):
            paths["roaming"] = roaming
        if os.path.exists(local):
            paths["local"] = local
            
        return paths
    
    def save_config(self):
        """Save current configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            logger.info(f"Configuration saved to {self.config_file}")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
