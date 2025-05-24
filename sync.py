import os
import sys
import logging
import configparser
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Set, Tuple, Optional
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from tqdm import tqdm
import fnmatch
from boto3.session import Config

from config import ZenSyncConfig
from utils import calculate_file_hash, format_size

logger = logging.getLogger(__name__)

class ZenS3Sync:
    """Main sync class for Zen Browser profiles"""
    
    def __init__(self, config: ZenSyncConfig, require_s3: bool = True):
        self.config = config
        self.s3_client = None
        self.bucket = config.config['aws']['bucket']
        self.prefix = config.config['aws']['prefix']
        
        self._initialize_paths()
        
        self.exclude_patterns = config.config['sync']['exclude_patterns']
        self.include_patterns = config.config['sync']['include_important']
        
        if require_s3:
            if not self.bucket:
                raise ValueError("S3 bucket name must be configured")
            self._init_s3_client()
    
    def _initialize_paths(self):
        """Initialize Zen browser paths"""
        sync_config = self.config.config['sync']
        auto_paths = self.config.auto_detect_zen_paths()
        
        self.zen_roaming_path = Path(sync_config['zen_roaming_path'] or auto_paths['roaming'] or '')
        self.zen_local_path = Path(sync_config['zen_local_path'] or auto_paths['local'] or '')
        
        logger.info(f"Zen Browser paths:")
        logger.info(f"  Roaming: {self.zen_roaming_path}")
        logger.info(f"  Local: {self.zen_local_path}")
        
        if not self.zen_roaming_path.exists():
            logger.warning(f"Roaming path does not exist: {self.zen_roaming_path}")
        if not self.zen_local_path.exists():
            logger.warning(f"Local path does not exist: {self.zen_local_path}")
    
    def _init_s3_client(self):
        """Initialize S3 client"""
        try:
            aws_config = self.config.config['aws']
            
            session_kwargs = {}
            client_kwargs = {'region_name': aws_config['region']}
            
            config_settings = {}
            if aws_config.get('signature_version'):
                config_settings['signature_version'] = aws_config['signature_version']
            
            if aws_config.get('endpoint_url'):
                client_kwargs['endpoint_url'] = aws_config['endpoint_url']
                config_settings['s3'] = {'addressing_style': 'path'}
                logger.info(f"Using S3 endpoint: {aws_config['endpoint_url']}")
            
            if config_settings:
                client_kwargs['config'] = Config(**config_settings)
            
            if aws_config.get('profile'):
                session_kwargs['profile_name'] = aws_config['profile']
                logger.info(f"Using AWS profile: {aws_config['profile']}")
            elif aws_config.get('access_key_id') and aws_config.get('secret_access_key'):
                client_kwargs.update({
                    'aws_access_key_id': aws_config['access_key_id'],
                    'aws_secret_access_key': aws_config['secret_access_key']
                })
                logger.warning("Using credentials from config file")
            
            if session_kwargs:
                session = boto3.Session(**session_kwargs)
                self.s3_client = session.client('s3', **client_kwargs)
            else:
                self.s3_client = boto3.client('s3', **client_kwargs)
            
            self.s3_client.head_bucket(Bucket=self.bucket)
            logger.info(f"Connected to S3, bucket: {self.bucket}")
            
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            sys.exit(1)
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.error(f"S3 bucket '{self.bucket}' not found")
            else:
                logger.error(f"Error connecting to S3: {e}")
            sys.exit(1)
    
    def _get_s3_key(self, file_path: Path, base_path: Path, path_type: str) -> str:
        relative_path = file_path.relative_to(base_path)
        if path_type in ['roaming', 'local']:
            return f"{self.prefix}{path_type}/{relative_path}".replace('\\', '/')
        return f"{self.prefix}{relative_path}".replace('\\', '/')

    def _get_relative_s3_key(self, file_path: Path, base_path: Path, path_type: str) -> str:
        relative_path = file_path.relative_to(base_path)
        if path_type in ['roaming', 'local']:
            return f"{path_type}/{relative_path}".replace('\\', '/')
        return str(relative_path).replace('\\', '/')

    def _get_download_path(self, relative_path: str) -> Optional[Path]:
        if relative_path.startswith('roaming/'):
            return self.zen_roaming_path / relative_path[8:] if self.zen_roaming_path else None
        elif relative_path.startswith('local/'):
            if self.zen_local_path and self.config.config['sync']['sync_cache_data']:
                return self.zen_local_path / relative_path[6:]
            return None
        return self.zen_roaming_path / relative_path if self.zen_roaming_path else None

    def _get_file_info(self, file_path: Path) -> Dict:
        """Get file information for comparison"""
        try:
            stat = file_path.stat()
            return {
                'size': stat.st_size,
                'mtime': int(stat.st_mtime),
                'hash': calculate_file_hash(file_path),
                'exists': True
            }
        except (OSError, FileNotFoundError):
            return {'exists': False}
    
    def _files_are_different(self, local_info: Dict, s3_info: Dict) -> bool:
        """Compare local file with S3 object"""
        if not local_info['exists'] or not s3_info['exists']:
            return True
        
        # Use hash comparison if available (apparently some s3 don't support putting custom metadata)
        if (local_info.get('hash') and s3_info.get('hash') and 
            local_info['hash'] and s3_info['hash']):
            are_different = local_info['hash'] != s3_info['hash']
            if are_different:
                logger.debug(f"Hash comparison: files different")
            else:
                logger.debug(f"Hash comparison: files identical")
            return are_different
        
        # Fallback to size comparison
        if local_info['size'] != s3_info['size']:
            logger.debug(f"Size comparison: files different")
            return True
        
        logger.debug(f"Size comparison: files identical")
        return False
    
    def _list_s3_objects(self) -> Dict[str, Dict]:
        """List all S3 objects with metadata"""
        objects = {}
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket, Prefix=self.prefix)
            
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        relative_key = obj['Key'][len(self.prefix):]
                        
                        obj_info = {
                            'size': obj['Size'],
                            'mtime': int(obj['LastModified'].timestamp()),
                            'etag': obj['ETag'].strip('"'),
                            'exists': True,
                            's3_key': obj['Key'],
                            'hash': None
                        }
                        
                        # Try to get hash from metadata
                        try:
                            head_response = self.s3_client.head_object(Bucket=self.bucket, Key=obj['Key'])
                            if 'Metadata' in head_response and not self.config.config['aws'].get('disable_metadata', False):
                                metadata = head_response['Metadata']
                                if 'file-hash' in metadata:
                                    obj_info['hash'] = metadata['file-hash']
                                elif 'file_hash' in metadata:
                                    obj_info['hash'] = metadata['file_hash']
                        except Exception:
                            pass
                        
                        objects[relative_key] = obj_info
                        
        except Exception as e:
            logger.error(f"Error listing S3 objects: {e}")
        
        return objects 

    def _log_sync_analysis(self, upload_files: List, download_files: List, skip_files: List, delete_files: List = None):
        total_upload_size = sum(item[2] for item in upload_files)
        total_download_size = sum(item[2] for item in download_files)
        total_skip_size = sum(item[2] for item in skip_files)
        
        logger.info(f"Sync analysis:")
        logger.info(f"  Upload: {len(upload_files)} files ({format_size(total_upload_size)})")
        logger.info(f"  Download: {len(download_files)} files ({format_size(total_download_size)})")
        logger.info(f"  Skip: {len(skip_files)} files ({format_size(total_skip_size)})")
        
        if delete_files:
            total_delete_size = sum(item[2] for item in delete_files)
            logger.info(f"  Delete: {len(delete_files)} files ({format_size(total_delete_size)})")

    def _process_files(self, files: List, action: str, dry_run: bool, processor_func) -> bool:
        if not files:
            return True
            
        logger.info(f"{'[DRY RUN] ' if dry_run else ''}{action.capitalize()} {len(files)} files...")
        success_count = 0
        error_count = 0
        
        with tqdm(total=len(files), desc=action.capitalize(), unit="file") as pbar:
            for file_args in files:
                try:
                    if not dry_run:
                        processor_func(*file_args)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Error {action} {file_args[0]}: {e}")
                    error_count += 1
                pbar.update(1)
        
        return error_count == 0

    def should_include_file(self, file_path: Path, base_path: Path) -> bool:
        """Check if file should be included in sync"""
        relative_path = file_path.relative_to(base_path)
        str_path = str(relative_path).replace('\\', '/')

        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(str_path, pattern) or fnmatch.fnmatch(file_path.name, pattern):
                return False

        for pattern in self.include_patterns:
            if fnmatch.fnmatch(str_path, pattern) or fnmatch.fnmatch(file_path.name, pattern):
                return True
        
        return True
    
    def get_local_files(self) -> List[tuple]:
        """Get list of local files to sync"""
        files = []
        
        if self.zen_roaming_path and self.zen_roaming_path.exists():
            roaming_files = self._scan_directory(self.zen_roaming_path, 'roaming')
            files.extend(roaming_files)
            logger.info(f"Found {len(roaming_files)} files in roaming directory")
        else:
            logger.error("Roaming directory not found")
            return []
        
        if (self.zen_local_path and self.zen_local_path.exists() and 
            self.config.config['sync']['sync_cache_data']):
            local_files = self._scan_directory(self.zen_local_path, 'local')
            files.extend(local_files)
            logger.info(f"Found {len(local_files)} files in local directory")
        
        logger.info(f"Total files to sync: {len(files)}")
        return files
    
    def _scan_directory(self, base_path: Path, path_type: str) -> List[tuple]:
        """Scan directory for files to sync"""
        files = []
        
        for root, dirs, filenames in os.walk(base_path):
            root_path = Path(root)
            
            dirs_to_skip = []
            for d in dirs:
                should_skip = False
                has_important_files = False
                
                for pattern in self.exclude_patterns:
                    if '/' in pattern:
                        dir_pattern = pattern.split('/')[0]
                        if fnmatch.fnmatch(d, dir_pattern):
                            should_skip = True
                            break
                
                if should_skip:
                    for pattern in self.include_patterns:
                        if '/' in pattern:
                            dir_pattern = pattern.split('/')[0]
                            if fnmatch.fnmatch(d, dir_pattern):
                                has_important_files = True
                                break
                
                if should_skip and not has_important_files:
                    dirs_to_skip.append(d)
            
            for d in dirs_to_skip:
                dirs.remove(d)
            
            for filename in filenames:
                file_path = root_path / filename
                if self.should_include_file(file_path, base_path):
                    files.append((file_path, base_path, path_type))
        
        return files
    
    def upload_to_s3(self, dry_run: bool = False, incremental: bool = True, cleanup: bool = False) -> bool:
        """Upload local Zen data to S3"""
        files = self.get_local_files()
        if not files:
            logger.warning("No files found to upload")
            return False
        
        s3_objects = {}
        if incremental or cleanup:
            logger.info("Analyzing existing S3 objects...")
            s3_objects = self._list_s3_objects()
        
        files_to_upload, files_to_skip, files_to_delete = self._analyze_upload_files(files, s3_objects, incremental, cleanup)
        
        self._log_sync_analysis(files_to_upload, [], files_to_skip, files_to_delete if cleanup else None)
        
        if not files_to_upload and not files_to_delete:
            logger.info("Everything is up to date!")
            return True
        
        upload_success = self._process_files(files_to_upload, "uploading", dry_run, self._upload_file_wrapper)
        delete_success = True
        
        if cleanup and files_to_delete:
            delete_success = self._process_files(files_to_delete, "deleting", dry_run, self._delete_s3_file)
        
        logger.info(f"Upload completed")
        return upload_success and delete_success

    def _analyze_upload_files(self, files: List, s3_objects: Dict, incremental: bool, cleanup: bool) -> Tuple[List, List, List]:
        files_to_upload = []
        files_to_skip = []
        files_to_delete = []
        
        logger.info(f"Analyzing {len(files)} local files...")
        
        for file_path, base_path, path_type in files:
            s3_key = self._get_s3_key(file_path, base_path, path_type)
            relative_s3_key = self._get_relative_s3_key(file_path, base_path, path_type)
            local_info = self._get_file_info(file_path)
            
            if incremental and relative_s3_key in s3_objects:
                s3_info = s3_objects[relative_s3_key]
                if not self._files_are_different(local_info, s3_info):
                    files_to_skip.append((file_path, s3_key, local_info['size']))
                    continue
            
            files_to_upload.append((file_path, s3_key, local_info['size'], path_type))
        
        if cleanup:
            local_s3_keys = {self._get_relative_s3_key(fp, bp, pt) for fp, bp, pt in files}
            for s3_key in s3_objects:
                if s3_key not in local_s3_keys:
                    s3_info = s3_objects[s3_key]
                    files_to_delete.append((s3_key, s3_info['s3_key'], s3_info['size']))
        
        return files_to_upload, files_to_skip, files_to_delete

    def download_from_s3(self, dry_run: bool = False, incremental: bool = True, cleanup: bool = False) -> bool:
        """Download Zen data from S3"""
        try:
            logger.info("Analyzing S3 objects...")
            s3_objects = self._list_s3_objects()
            
            if not s3_objects:
                logger.warning(f"No objects found in S3 with prefix: {self.prefix}")
                return False
            
            files_to_download, files_to_skip, files_to_delete = self._analyze_download_files(s3_objects, incremental, cleanup)
            
            self._log_sync_analysis([], files_to_download, files_to_skip, files_to_delete if cleanup else None)
            
            if not files_to_download and not files_to_delete:
                logger.info("Everything is up to date!")
                return True
            
            download_success = self._process_files(files_to_download, "downloading", dry_run, self._download_file_wrapper)
            delete_success = True
            
            if cleanup and files_to_delete:
                delete_success = self._process_files(files_to_delete, "deleting local", dry_run, self._delete_local_file)
            
            logger.info(f"Download completed")
            return download_success and delete_success
            
        except Exception as e:
            logger.error(f"Error during download: {e}")
            return False

    def _analyze_download_files(self, s3_objects: Dict, incremental: bool, cleanup: bool) -> Tuple[List, List, List]:
        files_to_download = []
        files_to_skip = []
        files_to_delete = []
        
        logger.info(f"Analyzing {len(s3_objects)} S3 objects...")
        
        for relative_s3_key, s3_info in s3_objects.items():
            local_path = self._get_download_path(relative_s3_key)
            if not local_path:
                continue
            
            local_info = self._get_file_info(local_path)
            
            if incremental and local_info['exists']:
                if not self._files_are_different(local_info, s3_info):
                    files_to_skip.append((local_path, s3_info['s3_key'], s3_info['size']))
                    continue
            
            files_to_download.append((local_path, s3_info['s3_key'], s3_info['size'], relative_s3_key))
        
        if cleanup:
            local_files = self.get_local_files()
            s3_relative_keys = set(s3_objects.keys())
            
            for file_path, base_path, path_type in local_files:
                relative_s3_key = self._get_relative_s3_key(file_path, base_path, path_type)
                if relative_s3_key not in s3_relative_keys:
                    file_info = self._get_file_info(file_path)
                    if file_info['exists']:
                        files_to_delete.append((file_path, relative_s3_key, file_info['size']))
        
        return files_to_download, files_to_skip, files_to_delete

    def sync_bidirectional(self, dry_run: bool = False, cleanup: bool = False) -> bool:
        """Perform bidirectional sync between local and S3"""
        logger.info("Starting bidirectional sync...")
        
        local_files = self.get_local_files()
        s3_objects = self._list_s3_objects()
        
        local_lookup = {}
        for file_path, base_path, path_type in local_files:
            relative_s3_key = self._get_relative_s3_key(file_path, base_path, path_type)
            local_lookup[relative_s3_key] = {
                'path': file_path,
                'info': self._get_file_info(file_path),
                'path_type': path_type
            }
        
        upload_files, download_files, skip_files = self._analyze_bidirectional_sync(local_lookup, s3_objects)
        
        self._log_sync_analysis(upload_files, download_files, skip_files)
        
        if not upload_files and not download_files:
            logger.info("Everything is in sync!")
            return True
        
        upload_success = self._process_files(upload_files, "uploading", dry_run, self._upload_file_wrapper)
        download_success = self._process_files(download_files, "downloading", dry_run, self._download_file_wrapper)
        
        logger.info("Bidirectional sync completed!")
        return upload_success and download_success

    def _analyze_bidirectional_sync(self, local_lookup: Dict, s3_objects: Dict) -> Tuple[List, List, List]:
        upload_files = []
        download_files = []
        skip_files = []
        
        for relative_key in set(local_lookup.keys()) & set(s3_objects.keys()):
            local_info = local_lookup[relative_key]['info']
            s3_info = s3_objects[relative_key]
            
            if not self._files_are_different(local_info, s3_info):
                skip_files.append((relative_key, None, local_info['size']))
                continue
            
            if local_info['mtime'] > s3_info['mtime']:
                file_path = local_lookup[relative_key]['path']
                path_type = local_lookup[relative_key]['path_type']
                s3_key = s3_objects[relative_key]['s3_key']
                upload_files.append((file_path, s3_key, local_info['size'], path_type))
            else:
                local_path = local_lookup[relative_key]['path']
                s3_key = s3_objects[relative_key]['s3_key']
                download_files.append((local_path, s3_key, s3_info['size'], relative_key))
        
        for relative_key in set(local_lookup.keys()) - set(s3_objects.keys()):
            local_data = local_lookup[relative_key]
            file_path = local_data['path']
            path_type = local_data['path_type']
            
            base_path = self.zen_roaming_path if path_type == 'roaming' else self.zen_local_path
            s3_key = self._get_s3_key(file_path, base_path, path_type)
            upload_files.append((file_path, s3_key, local_data['info']['size'], path_type))
        
        for relative_key in set(s3_objects.keys()) - set(local_lookup.keys()):
            s3_info = s3_objects[relative_key]
            local_path = self._get_download_path(relative_key)
            if local_path:
                download_files.append((local_path, s3_info['s3_key'], s3_info['size'], relative_key))
        
        return upload_files, download_files, skip_files

    def _upload_file_wrapper(self, file_path: Path, s3_key: str, size: int, path_type: str):
        self._upload_file(file_path, s3_key, path_type)

    def _download_file_wrapper(self, local_path: Path, s3_key: str, size: int, relative_key: str):
        self._download_file(s3_key, local_path)

    def _delete_s3_file(self, relative_key: str, s3_key: str, size: int):
        self.s3_client.delete_object(Bucket=self.bucket, Key=s3_key)

    def _delete_local_file(self, file_path: Path, relative_key: str, size: int):
        file_path.unlink()
        try:
            file_path.parent.rmdir()
        except OSError:
            pass
    
    def _upload_file(self, file_path: Path, s3_key: str, path_type: str):
        """Upload a single file to S3"""
        if not self.config.config['aws'].get('disable_metadata', False):
            file_hash = calculate_file_hash(file_path)
            metadata = {
                'path-type': path_type,
                'original-mtime': str(int(file_path.stat().st_mtime)),
                'file-hash': file_hash
            }
            
            try:
                with open(file_path, 'rb') as file_data:
                    self.s3_client.put_object(
                        Bucket=self.bucket,
                        Key=s3_key,
                        Body=file_data,
                        Metadata=metadata
                    )
            except ClientError as e:
                error_msg = str(e)
                if ('AccessDenied' in error_msg or 'headers' in error_msg.lower() or 
                    'not signed' in error_msg or 'signature' in error_msg.lower()):
                    logger.warning(f"Metadata error, retrying without metadata for {file_path.name}")
                    with open(file_path, 'rb') as file_data:
                        self.s3_client.put_object(
                            Bucket=self.bucket,
                            Key=s3_key,
                            Body=file_data
                        )
                    if not self.config.config['aws'].get('disable_metadata', False):
                        self.config.config['aws']['disable_metadata'] = True
                        self.config.save_config()
                        logger.info("Auto-disabled metadata for compatibility")
                else:
                    raise
        else:
            with open(file_path, 'rb') as file_data:
                self.s3_client.put_object(
                    Bucket=self.bucket,
                    Key=s3_key,
                    Body=file_data
                )
    
    def _download_file(self, s3_key: str, local_path: Path):
        """Download a single file from S3"""
        local_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.s3_client.download_file(
            self.bucket,
            s3_key,
            str(local_path)
        )
        
        # Try to restore modification time
        try:
            obj_metadata = self.s3_client.head_object(Bucket=self.bucket, Key=s3_key)
            if ('Metadata' in obj_metadata and
                not self.config.config['aws'].get('disable_metadata', False)):
                metadata = obj_metadata['Metadata']
                original_mtime = None
                if 'original-mtime' in metadata:
                    original_mtime = int(metadata['original-mtime'])
                elif 'original_mtime' in metadata:
                    original_mtime = int(metadata['original_mtime'])
                
                if original_mtime:
                    os.utime(local_path, (original_mtime, original_mtime))
        except Exception:
            pass
    
    def list_profiles(self) -> Dict:
        """List available Zen browser profiles"""
        profiles = {}
        
        if self.zen_roaming_path:
            profiles.update(self._list_profiles_from_path(self.zen_roaming_path, "roaming"))
        else:
            logger.error("Roaming path not configured")
        
        return profiles
    
    def _list_profiles_from_path(self, zen_path: Path, path_type: str) -> Dict:
        """List profiles from a specific path"""
        profiles = {}
        profiles_ini = zen_path / "profiles.ini"
        
        if not profiles_ini.exists():
            logger.warning(f"profiles.ini not found in {zen_path}")
            return profiles
        
        try:
            config_parser = configparser.ConfigParser()
            config_parser.read(profiles_ini)
            
            for section in config_parser.sections():
                if section.startswith('Profile'):
                    name = config_parser.get(section, 'Name', fallback='Unknown')
                    path = config_parser.get(section, 'Path', fallback='')
                    is_default = config_parser.getboolean(section, 'Default', fallback=False)
                    store_id = config_parser.get(section, 'StoreID', fallback='')
                    
                    profile_path = zen_path / 'Profiles' / path if path else None
                    
                    profiles[section] = {
                        'name': name,
                        'path': path,
                        'is_default': is_default,
                        'store_id': store_id,
                        'full_path': profile_path,
                        'path_type': path_type,
                        'base_path': zen_path
                    }
        except Exception as e:
            logger.error(f"Error reading profiles.ini from {zen_path}: {e}")
        
        return profiles
    
    def get_profile_info(self) -> Dict:
        """Get comprehensive profile information"""
        info = {
            'system_type': 'dual-path',
            'paths': {},
            'profiles': {},
            'profile_groups': {}
        }
        
        info['paths'] = {
            'roaming': str(self.zen_roaming_path) if self.zen_roaming_path else 'Not configured',
            'local': str(self.zen_local_path) if self.zen_local_path else 'Not configured',
            'roaming_exists': self.zen_roaming_path.exists() if self.zen_roaming_path else False,
            'local_exists': self.zen_local_path.exists() if self.zen_local_path else False
        }
        
        info['profiles'] = self.list_profiles()
        
        if self.zen_roaming_path:
            profile_groups_dir = self.zen_roaming_path / "Profile Groups"
            if profile_groups_dir.exists():
                info['profile_groups']['exists'] = True
                info['profile_groups']['path'] = str(profile_groups_dir)
                db_files = list(profile_groups_dir.glob("*.sqlite"))
                info['profile_groups']['databases'] = [f.name for f in db_files]
            else:
                info['profile_groups']['exists'] = False
        
        return info
