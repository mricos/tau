"""
TRS (Tetra Record Specification) storage layer for ASCII Scope SNN.

Implements context-aware, filesystem-based database pattern using:
- Canonical location: ./db/ (local working directory)
- Naming: timestamp.type.kind.format
- Module name: 'asnn' (implicit in canonical location)
"""

import os
import time
import json
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass


@dataclass
class TRSRecord:
    """TRS record metadata."""
    filepath: Path
    timestamp: int
    attributes: Dict[str, str]  # type, kind, etc.
    format: str

    @classmethod
    def from_path(cls, filepath: Path) -> 'TRSRecord':
        """Parse TRS record from filepath."""
        filename = filepath.name
        parts = filename.split('.')

        if len(parts) < 3:
            raise ValueError(f"Invalid TRS filename: {filename}")

        timestamp = int(parts[0])
        format_ext = parts[-1]
        attribute_parts = parts[1:-1]

        # Parse attributes (order-independent)
        attributes = {}
        for i, part in enumerate(attribute_parts):
            # Try to infer attribute type
            if i == 0:
                attributes['type'] = part
            elif i == 1:
                attributes['kind'] = part
            else:
                attributes[f'attr{i}'] = part

        return cls(
            filepath=filepath,
            timestamp=timestamp,
            attributes=attributes,
            format=format_ext
        )

    def matches(self, **filters) -> bool:
        """Check if record matches filters."""
        for key, value in filters.items():
            if key == 'timestamp':
                if self.timestamp != value:
                    return False
            elif key == 'format':
                if self.format != value:
                    return False
            elif key not in self.attributes or self.attributes[key] != value:
                return False
        return True


class TRSStorage:
    """
    TRS storage manager for ASCII Scope SNN.

    Manages canonical location (./db/) with implicit module naming.
    """

    MODULE_NAME = "asnn"

    def __init__(self, db_path: str = "./db"):
        """
        Initialize TRS storage.

        Args:
            db_path: Path to canonical database directory (default: ./db)
        """
        self.db_path = Path(db_path).resolve()
        self.db_path.mkdir(parents=True, exist_ok=True)

    def write(self,
              type: str,
              kind: str,
              format: str,
              data: Any,
              timestamp: Optional[int] = None,
              **extra_attrs) -> Path:
        """
        Write data to TRS record in canonical location.

        Args:
            type: Record type (data, config, session, log, audio)
            kind: Record kind (raw, kernel, state, event, source)
            format: File format (tsv, toml, json, jsonl, wav)
            data: Data to write (string, bytes, or dict/list for JSON)
            timestamp: Optional timestamp (default: current time)
            **extra_attrs: Additional attributes to include in filename

        Returns:
            Path to created file

        Example:
            trs.write("data", "raw", "tsv", tsv_data)
            # Creates: ./db/1730745600.data.raw.tsv
        """
        if timestamp is None:
            timestamp = int(time.time())

        # Build filename: timestamp.type.kind[.extra...].format
        parts = [str(timestamp), type, kind]

        # Add extra attributes
        for key in sorted(extra_attrs.keys()):
            parts.append(extra_attrs[key])

        parts.append(format)
        filename = '.'.join(parts)
        filepath = self.db_path / filename

        # Write data based on format
        if format in ('json', 'jsonl'):
            with open(filepath, 'w') as f:
                if format == 'jsonl':
                    # Write as JSON Lines
                    if isinstance(data, list):
                        for item in data:
                            f.write(json.dumps(item) + '\n')
                    else:
                        f.write(json.dumps(data) + '\n')
                else:
                    json.dump(data, f, indent=2)
        elif isinstance(data, bytes):
            with open(filepath, 'wb') as f:
                f.write(data)
        else:
            with open(filepath, 'w') as f:
                f.write(str(data))

        return filepath

    def write_file(self,
                   type: str,
                   kind: str,
                   source_path: Path,
                   timestamp: Optional[int] = None,
                   **extra_attrs) -> Path:
        """
        Copy file to TRS location.

        Args:
            type: Record type
            kind: Record kind
            source_path: Path to source file
            timestamp: Optional timestamp
            **extra_attrs: Additional attributes

        Returns:
            Path to created file
        """
        source_path = Path(source_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        format_ext = source_path.suffix.lstrip('.')

        with open(source_path, 'rb') as f:
            data = f.read()

        return self.write(type, kind, format_ext, data,
                          timestamp=timestamp, **extra_attrs)

    def query(self, **filters) -> List[TRSRecord]:
        """
        Query TRS records by attributes.

        Args:
            **filters: Filter criteria (type, kind, format, timestamp, etc.)

        Returns:
            List of matching TRSRecord objects, sorted by timestamp (newest first)

        Examples:
            trs.query(type="data", kind="raw")
            trs.query(timestamp=1730745600)
            trs.query(format="tsv")
        """
        results = []

        for filepath in self.db_path.glob("*"):
            if not filepath.is_file():
                continue

            # Skip non-TRS files
            if not filepath.name[0].isdigit():
                continue

            try:
                record = TRSRecord.from_path(filepath)
                if record.matches(**filters):
                    results.append(record)
            except (ValueError, IndexError):
                # Skip malformed filenames
                continue

        # Sort by timestamp, newest first
        results.sort(key=lambda r: r.timestamp, reverse=True)
        return results

    def query_latest(self, **filters) -> Optional[TRSRecord]:
        """
        Get latest record matching filters.

        Args:
            **filters: Filter criteria

        Returns:
            Latest matching record or None
        """
        results = self.query(**filters)
        return results[0] if results else None

    def query_timestamp(self, timestamp: int) -> List[TRSRecord]:
        """
        Get all records for a specific timestamp.

        Args:
            timestamp: Unix timestamp

        Returns:
            List of records with matching timestamp
        """
        return self.query(timestamp=timestamp)

    def read(self, record: TRSRecord) -> Any:
        """
        Read data from TRS record.

        Args:
            record: TRSRecord to read

        Returns:
            Parsed data (dict/list for JSON, string for text, bytes for binary)
        """
        filepath = record.filepath

        if record.format in ('json', 'jsonl'):
            with open(filepath, 'r') as f:
                if record.format == 'jsonl':
                    return [json.loads(line) for line in f if line.strip()]
                else:
                    return json.load(f)
        elif record.format in ('tsv', 'txt', 'toml', 'md'):
            with open(filepath, 'r') as f:
                return f.read()
        else:
            # Binary format
            with open(filepath, 'rb') as f:
                return f.read()

    def read_latest(self, **filters) -> Optional[Any]:
        """
        Read latest record matching filters.

        Args:
            **filters: Filter criteria

        Returns:
            Parsed data from latest record or None
        """
        record = self.query_latest(**filters)
        return self.read(record) if record else None

    def delete(self, record: TRSRecord) -> bool:
        """
        Delete a TRS record.

        Args:
            record: Record to delete

        Returns:
            True if deleted successfully
        """
        try:
            record.filepath.unlink()
            return True
        except Exception:
            return False

    def get_db_size(self) -> int:
        """Get total size of database in bytes."""
        total = 0
        for filepath in self.db_path.glob("*"):
            if filepath.is_file():
                total += filepath.stat().st_size
        return total

    def list_all(self, limit: Optional[int] = None) -> List[TRSRecord]:
        """
        List all records, newest first.

        Args:
            limit: Optional limit on number of records

        Returns:
            List of all TRSRecord objects
        """
        records = self.query()
        if limit:
            return records[:limit]
        return records

    def export(self, record: TRSRecord, dest_dir: Path) -> Path:
        """
        Export record to non-canonical location with explicit module naming.

        Args:
            record: Record to export
            dest_dir: Destination directory

        Returns:
            Path to exported file

        Example:
            trs.export(record, Path("/tmp/export"))
            # Creates: /tmp/export/1730745600.asnn.data.raw.tsv
        """
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Build new filename with explicit module
        parts = [str(record.timestamp), self.MODULE_NAME]
        parts.extend(record.attributes.values())
        parts.append(record.format)
        export_name = '.'.join(parts)

        dest_path = dest_dir / export_name

        # Copy file
        import shutil
        shutil.copy2(record.filepath, dest_path)

        return dest_path
