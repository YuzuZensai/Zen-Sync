import argparse
import sys
import json
import logging
from config import ZenSyncConfig
from sync import ZenS3Sync

logger = logging.getLogger(__name__)

def create_parser():
    parser = argparse.ArgumentParser(
        description="Zen Browser Profile S3 Sync Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  zensync upload --bucket my-backup-bucket
  zensync download --bucket my-backup-bucket
  zensync sync --bucket my-backup-bucket
  zensync configure --bucket my-bucket --endpoint-url http://localhost:9000
  zensync list-profiles
        """
    )
    
    parser.add_argument('--config', default='zen_sync_config.json', help='Configuration file path')
    parser.add_argument('--roaming-path', help='Override Zen roaming data path')
    parser.add_argument('--local-path', help='Override Zen local data path')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Upload command
    upload_parser = subparsers.add_parser('upload', help='Upload profiles to S3')
    upload_parser.add_argument('--bucket', help='S3 bucket name')
    upload_parser.add_argument('--prefix', default='zen-profiles/', help='S3 key prefix')
    upload_parser.add_argument('--dry-run', action='store_true', help='Show what would be uploaded')
    upload_parser.add_argument('--no-cache', action='store_true', help='Disable cache data upload')
    upload_parser.add_argument('--force-full', action='store_true', help='Force full upload')
    upload_parser.add_argument('--cleanup', action='store_true', help='Remove S3 files that no longer exist locally')
    
    # Download command
    download_parser = subparsers.add_parser('download', help='Download profiles from S3')
    download_parser.add_argument('--bucket', help='S3 bucket name')
    download_parser.add_argument('--prefix', default='zen-profiles/', help='S3 key prefix')
    download_parser.add_argument('--dry-run', action='store_true', help='Show what would be downloaded')
    download_parser.add_argument('--no-cache', action='store_true', help='Disable cache data download')
    download_parser.add_argument('--force-full', action='store_true', help='Force full download')
    download_parser.add_argument('--cleanup', action='store_true', help='Remove local files that no longer exist in S3')
    
    # Sync command
    sync_parser = subparsers.add_parser('sync', help='Bidirectional sync between local and S3')
    sync_parser.add_argument('--bucket', help='S3 bucket name')
    sync_parser.add_argument('--prefix', default='zen-profiles/', help='S3 key prefix')
    sync_parser.add_argument('--dry-run', action='store_true', help='Show what would be synced')
    sync_parser.add_argument('--no-cache', action='store_true', help='Disable cache data sync')
    sync_parser.add_argument('--cleanup', action='store_true', help='Remove orphaned files')
    
    # List profiles command
    subparsers.add_parser('list-profiles', help='List available local profiles')
    
    # Profile info command
    subparsers.add_parser('profile-info', help='Show profile system information')
    
    # Configure command
    config_parser = subparsers.add_parser('configure', help='Configure sync settings')
    config_parser.add_argument('--bucket', help='Set S3 bucket name')
    config_parser.add_argument('--region', help='Set AWS region')
    config_parser.add_argument('--endpoint-url', help='Set S3-compatible service endpoint')
    config_parser.add_argument('--access-key', help='Set AWS access key ID')
    config_parser.add_argument('--secret-key', help='Set AWS secret access key')
    config_parser.add_argument('--profile', help='Set AWS profile name')
    config_parser.add_argument('--roaming-path', help='Set Zen roaming data path')
    config_parser.add_argument('--local-path', help='Set Zen local data path')
    config_parser.add_argument('--auto-detect', action='store_true', help='Auto-detect Zen browser paths')
    config_parser.add_argument('--enable-cache-sync', action='store_true', help='Enable cache data sync')
    config_parser.add_argument('--disable-cache-sync', action='store_true', help='Disable cache data sync')
    config_parser.add_argument('--disable-metadata', action='store_true', help='Disable S3 metadata')
    config_parser.add_argument('--enable-metadata', action='store_true', help='Enable S3 metadata')
    config_parser.add_argument('--signature-version', choices=['s3', 's3v4'], help='Set AWS signature version')
    
    return parser

def handle_configure(args, config):
    """Handle configure command"""
    if args.bucket:
        config.config['aws']['bucket'] = args.bucket
    if args.region:
        config.config['aws']['region'] = args.region
    if getattr(args, 'endpoint_url', None):
        config.config['aws']['endpoint_url'] = args.endpoint_url
        logger.info(f"Using custom S3 endpoint: {args.endpoint_url}")
    if args.access_key:
        config.config['aws']['access_key_id'] = args.access_key
        logger.warning("Storing AWS access key in config file")
    if args.secret_key:
        config.config['aws']['secret_access_key'] = args.secret_key
        logger.warning("Storing AWS secret key in config file")
    if args.profile:
        config.config['aws']['profile'] = args.profile
        config.config['aws']['access_key_id'] = ""
        config.config['aws']['secret_access_key'] = ""
        logger.info(f"Configured to use AWS profile: {args.profile}")
    if args.roaming_path:
        config.config['sync']['zen_roaming_path'] = args.roaming_path
    if args.local_path:
        config.config['sync']['zen_local_path'] = args.local_path
    
    if args.auto_detect:
        auto_paths = config.auto_detect_zen_paths()
        if auto_paths['roaming']:
            config.config['sync']['zen_roaming_path'] = auto_paths['roaming']
            print(f"Auto-detected roaming path: {auto_paths['roaming']}")
        if auto_paths['local']:
            config.config['sync']['zen_local_path'] = auto_paths['local']
            print(f"Auto-detected local path: {auto_paths['local']}")
    
    if args.enable_cache_sync:
        config.config['sync']['sync_cache_data'] = True
    if args.disable_cache_sync:
        config.config['sync']['sync_cache_data'] = False
    if getattr(args, 'disable_metadata', False):
        config.config['aws']['disable_metadata'] = True
        logger.info("S3 metadata disabled")
    if getattr(args, 'enable_metadata', False):
        config.config['aws']['disable_metadata'] = False
        logger.info("S3 metadata enabled")
    if getattr(args, 'signature_version', None):
        config.config['aws']['signature_version'] = args.signature_version
        logger.info(f"AWS signature version set to: {args.signature_version}")
    
    config.save_config()
    
    display_config = json.loads(json.dumps(config.config))
    if display_config['aws'].get('secret_access_key'):
        display_config['aws']['secret_access_key'] = "***HIDDEN***"
    
    print("\nConfiguration updated:")
    print(json.dumps(display_config, indent=2))

def handle_list_profiles(sync):
    """Handle list-profiles command"""
    profiles = sync.list_profiles()
    if profiles:
        print(f"\nAvailable Zen Browser Profiles:")
        print("=" * 70)
        for profile_id, info in profiles.items():
            status = " (Default)" if info['is_default'] else ""
            print(f"• {info['name']}{status}")
            print(f"  Profile ID: {profile_id}")
            print(f"  Path: {info['path']}")
            print(f"  Store ID: {info.get('store_id', 'N/A')}")
            print(f"  Full Path: {info['full_path']}")
            print()
    else:
        print("No profiles found")

def handle_profile_info(sync):
    """Handle profile-info command"""
    info = sync.get_profile_info()
    print(f"\nZen Browser Profile System Information:")
    print("=" * 70)
    print(f"System Type: {info['system_type']}")
    print("\nPaths:")
    for path_name, path_value in info['paths'].items():
        print(f"  {path_name}: {path_value}")
    
    print(f"\nProfiles Found: {len(info['profiles'])}")
    if info['profiles']:
        for profile_id, profile_info in info['profiles'].items():
            status = " (Default)" if profile_info['is_default'] else ""
            print(f"  • {profile_info['name']}{status}")
    
    if 'profile_groups' in info:
        print(f"\nProfile Groups:")
        if info['profile_groups'].get('exists'):
            print(f"  Path: {info['profile_groups']['path']}")
            print(f"  Databases: {', '.join(info['profile_groups'].get('databases', []))}")
        else:
            print("  Not found")

def run_cli():
    """Main CLI entry point"""
    parser = create_parser()
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    config = ZenSyncConfig(args.config)
    
    if args.roaming_path:
        config.config['sync']['zen_roaming_path'] = args.roaming_path
    if args.local_path:
        config.config['sync']['zen_local_path'] = args.local_path
    
    if args.command == 'configure':
        handle_configure(args, config)
        return

    if args.command in ['upload', 'download', 'sync']:
        if args.bucket:
            config.config['aws']['bucket'] = args.bucket
        if args.prefix:
            config.config['aws']['prefix'] = args.prefix
        if hasattr(args, 'no_cache') and args.no_cache:
            config.config['sync']['sync_cache_data'] = False
            logger.info("Cache sync disabled for this operation")
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        require_s3 = args.command not in ['list-profiles', 'profile-info']
        if args.command in ['upload', 'download', 'sync'] and hasattr(args, 'dry_run') and args.dry_run:
            require_s3 = True
            logger.info("Dry run mode: Will analyze existing S3 objects")
        
        sync = ZenS3Sync(config, require_s3=require_s3)
        
        if args.command == 'upload':
            incremental = not getattr(args, 'force_full', False)
            cleanup = getattr(args, 'cleanup', False)
            success = sync.upload_to_s3(
                dry_run=args.dry_run, 
                incremental=incremental, 
                cleanup=cleanup
            )
            sys.exit(0 if success else 1)
            
        elif args.command == 'download':
            incremental = not getattr(args, 'force_full', False)
            cleanup = getattr(args, 'cleanup', False)
            success = sync.download_from_s3(
                dry_run=args.dry_run, 
                incremental=incremental, 
                cleanup=cleanup
            )
            sys.exit(0 if success else 1)
            
        elif args.command == 'sync':
            cleanup = getattr(args, 'cleanup', False)
            success = sync.sync_bidirectional(
                dry_run=args.dry_run, 
                cleanup=cleanup
            )
            sys.exit(0 if success else 1)
            
        elif args.command == 'list-profiles':
            handle_list_profiles(sync)
        
        elif args.command == 'profile-info':
            handle_profile_info(sync)
    
    except Exception as e:
        logger.error(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1) 
