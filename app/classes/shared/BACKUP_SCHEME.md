# Crafty Snapshot Backup Scheme

Snapshot backups make the use four types of files (more when encryption is
implemented). All files are versioned so that future versions of Crafty may make
changes while attempting to minimize potential sources of data loss.

The four types of files that Crafty makes use of for snapshot backups are:
- Backup manifest files.
- Backup depends files.
- Backup chunks files.
- Data chunk files.

# File description And Samples
## Backup manifest file (json)

Filename: `backup-id.json`

UTF-8 text encoded json file. First value must be "version" to allow Crafty to detect
and abort versions made with a future scheme.

Manifest data itself must allow for encryption to prevent leaking file names. File
names are defined as sensitive to scheme, file count or hash are not.

### Values
- Version: Integer showing version of file contents. Currently, 1.
- Backup ID: Unique ID associated with backup.
- Server ID: Server ID of associated server.
- Date: ISO 8601 timestamp of when backup was taken.
- Num_files: Number of files associated with backup.
- Num_bytes: Cumulative bytes of files associated with backup.
- Manifest_data_encrypted: Boolean indicating if manifest data is encrypted. Currently
unused but in version one to allow for encryption of manifest data.
- Manifest_data_compressed: Boolean indicating if manifest data is compressed.
- Encrypted_manifest_dek: Base64 encoded data encrypting nonce. Currently unused.
- Key_encrypting_nonce: Base64 encoded key encrypting nonce. Currently unused.
- Manifest_data: Base 64 encoded (potentially compressed and/or encrypted) json containing manifest data.

Sample:
```json
{
  "version": 1,
  "backup_id": "00000000-0000-0000-0000-000000000000",
  "server_id": "00000000-0000-0000-0000-000000000000",
  "date": "1970-01-01T00.00.00.0000",
  "num_files": 0,
  "num_bytes": 0,
  "manifest_data_encrypted": false,
  "manifest_data_compressed": false,
  "encrypted_manifest_dek": "c2FtcGxl",
  "key_encrypting_nonce": "c2FtcGxl",
  "data_encrypting_nonce": "c2FtcGxl",
  "manifest_data": "c2FtcGxl"
}
```

## Backup depends file (plain text)
Filename: `backup-id.depends`

UTF-8 text file containing lines of base64 file hashes. First line must contain version
information.Since manifest data be encrypted, an obfuscated list of files contained in
the backup must be available for the maintenance procedure. This file contains the hash
of all files in the backup so that they do not get deleted. For chunk data, only the
chunks should be contained as only the chunks are stored in the final repository.
Base64 is used as it takes up less data when encodes as UTF-8

During maintenance, a list of all current chunks can be found by combining the contents
of all depends files for current backups. Chunks found not in any current depends files
may be deleted.

### Sample:
```
1
Q4agiiZREcmJb1ZFbiy2GmQjkRXEeEz0OONsyFEiGXLaP7ARX3PNAkhiVAAfh4qx/RJqrGmETvHByhUjedCpvQ==
```

## Backup chunks file (json)
Filename: `backup-id.chunks`

Files larger than 500 mb will be split into chunks, the chunks file identifies what
chunked files are made of what chunks. All information in this file is hashed as file
names are sensitive information. Base64 encoding of chunks is used to optimize UTF-8
re-encoding.

Data is just the identifier of the chunked file, then a list of chunks contained in that file.

### Sample:
```json
{
  "version": 1,
  "chunked_file": {
    "Q4agiiZREcmJb1ZFbiy2GmQjkRXEeEz0OONsyFEiGXLaP7ARX3PNAkhiVAAfh4qx/RJqrGmETvHByhUjedCpvQ==": ["Q4agiiZREcmJb1ZFbiy2GmQjkRXEeEz0OONsyFEiGXLaP7ARX3PNAkhiVAAfh4qx/RJqrGmETvHByhUjedCpvQ==", "Q4agiiZREcmJb1ZFbiy2GmQjkRXEeEz0OONsyFEiGXLaP7ARX3PNAkhiVAAfh4qx/RJqrGmETvHByhUjedCpvQ=="],
    "Q4agiiZREcmJb1ZFbiy2GmQjkRXEeEz0OONsyFEiGXLaP7ARX3PNAkhiVAAfh4qx/RJqrGmETvHByhUjedCpvQ==": ["Q4agiiZREcmJb1ZFbiy2GmQjkRXEeEz0OONsyFEiGXLaP7ARX3PNAkhiVAAfh4qx/RJqrGmETvHByhUjedCpvQ==", "Q4agiiZREcmJb1ZFbiy2GmQjkRXEeEz0OONsyFEiGXLaP7ARX3PNAkhiVAAfh4qx/RJqrGmETvHByhUjedCpvQ=="],
  }
}
```


