# 🧘‍♀️ Zen-Sync 

A Windows only command-line tool for syncing [Zen Browser](https://zen-browser.app/) data with S3-compatible storage services.

## 🤔 What it does

Since Zen Browser doesn't have proper profile sync yet, this is my quick solution built in a few hours to keep my stuffs in sync across multiple machines.

It backs up all the important stuff to any S3-compatible cloud storage so you can restore or "sync" your profile anywhere. No more manually dragging around profile folders every time you edit a settings 🥹🥹😭. I'm so done with that.

The default (customizable) setting skips session cookies, temporary storage, and other data because sites I visit can detect copied sessions through fingerprinting and will invalidate them.

## ✨ Features

- 🔄 **Bidirectional sync** between local and S3 storage
- 🔍 **Filtering**  - only syncs important files, excludes cache and temporary data
- ⚡ **"Incremental" sync** - only uploads/downloads changed files
- 🔗 **Custom S3 endpoints** - works with any S3-compatible service

## 📋 What gets synced by default

**Included:** 
- 📁 Profile configuration (`profiles.ini`, `installs.ini`, `compatibility.ini`)
- 🗃️ Profile Groups databases (`Profile Groups/*.sqlite`)
- 📚 Bookmarks (`places.sqlite`, `bookmarks.html`)
- 🔒 Saved passwords and certificates (`key4.db`, `cert9.db`, `logins.json`)
- 🧩 Extensions and their settings (`extensions.json`, `extension-*.json`)
- 🎨 Custom themes and CSS (`zen-*.json`, `zen-*.css`, `userChrome.css`, `userContent.css`)
- ⚙️ Browser preferences (`prefs.js`, `user.js`)
- 🔍 Search engine settings (`search.json.mozlz4`)
- 🖼️ Favicons (`favicons.sqlite`)
- 📂 Chrome folder customizations (`chrome/**/*`)
- 📔 and other files from customizable ruleset

**Excluded:** 
- 🗑️ Cache files (`cache2/*`, `thumbnails/*`, `shader-cache/*`)
- 📜 Logs and crash reports (`logs/*`, `crashes/*`, `minidumps/*`)
- 🔒 Lock files (`*.lock`, `*.lck`, `parent.lock`)
- 💾 Temporary storage (`storage/temporary/*`, `storage/*/ls/*`)
- 📋 Session data (`sessionstore.jsonlz4`, `sessionCheckpoints.json`)
- 🍪 Session cookies (`cookies.sqlite*`)
- 🛡️ Temporary browsing data (`webappsstore.sqlite*`, `safebrowsing/*`)

Use `--help` with any command for detailed options. 

## 🚀 Quick Start

1. ⚙️ **Configure your S3 settings:**
   ```bash
   python zensync.py configure --bucket your-bucket-name --endpoint-url https://your-s3-endpoint.com
   ```

    or just run ```python zensync.py configure``` then edit the configuration json manually.

2. ⬆️ **Upload your profiles:**
   ```bash
   python zensync.py upload
   ```

3. ⬇️ **Download profiles on another machine:**
   ```bash
   python zensync.py download
   ```

4. 🔄 **Two-way sync:**
   ```bash
   python zensync.py sync
   ```

## Main Commands 🎮

- ⚙️ `configure` - Set up S3 credentials and paths
- ⬆️ `upload` - Backup profiles to S3
- ⬇️ `download` - Restore profiles from S3
- 🔄 `sync` - Bidirectional synchronization
- 📋 `list-profiles` - Show available local profiles
- ℹ️ `profile-info` - Display profile system information

## 📝 Configuration 

Settings are stored in `zen_sync_config.json`.
