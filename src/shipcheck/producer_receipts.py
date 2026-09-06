"""Read-only CC producer receipt interoperability; consistency can only veto.

A supplied hash is not an authenticated checkpoint. Candidate bindings in this
bundle are declarations, since CC receipts do not embed the assessed Git subject.
No producer is imported or executed and no native release trust is strengthened.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import math
import os
from pathlib import Path
import re
import stat

from .release_gate.artifacts import _open_beneath
from .release_gate.canonical import canonical_json, object_digest
from .release_gate.errors import SecurityError, ValidationError
from .release_gate.limits import loads_strict
from .release_gate.models import Candidate
from .release_gate.risk import normalize_repo_path

SCHEMA = 'shipcheck/producer-bundle-v1'
PRODUCERS = {'ai-software-factory', 'promptops', 'repo-doctor-ai', 'rag-lab', 'local-ai-stack'}
MAX_RECEIPT_BYTES = 1024 * 1024
MAX_ARTIFACT_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_FILES = 128
SHA = re.compile(r'[0-9a-f]{64}\Z')
RUN = re.compile(r'run-[0-9a-f]{32}\Z')
ID = re.compile(r'[a-z][a-z0-9-]{0,63}\Z')


def _require(condition, code):
    if not condition: raise ValidationError(code)


def _keys(value, required, optional=()):
    _require(type(value) is dict and set(required) <= set(value)
             and set(value) <= set(required) | set(optional), 'producer_fields_invalid')


def _sha(value):
    _require(type(value) is str and SHA.fullmatch(value) is not None, 'producer_digest_invalid')
    return value


def _number(value):
    try: valid = type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError: valid = False
    _require(valid, 'producer_timestamp_invalid')
    return value


def check_root(root):
    path = Path(root).absolute()
    _require('..' not in path.parts, 'producer_root_invalid')
    for part in (path, *path.parents):
        _require(not part.is_symlink() and not getattr(part, 'is_junction', lambda: False)(), 'producer_link_refused')
    _require(path.is_dir(), 'producer_root_invalid')
    return path


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink


class _Reader:
    def __init__(self, root):
        self.root = check_root(root)
        self.total = 0
        self.paths = set()
        self.identities = set()
        self.files = []

    def read(self, relative, maximum):
        normalized = normalize_repo_path(relative)
        _require(normalized == relative, 'producer_path_not_canonical')
        _require(relative not in self.paths, 'producer_duplicate_path')
        _require(len(self.paths) < MAX_FILES, 'producer_file_limit')
        self.paths.add(relative)
        target = self.root.joinpath(*relative.split('/'))
        for part in (target, *target.parents):
            _require(not part.is_symlink() and not getattr(part, 'is_junction', lambda: False)(), 'producer_link_refused')
        fd, _ = _open_beneath(self.root, relative)
        try:
            before = os.fstat(fd)
            _require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, 'producer_regular_single_link_required')
            identity = (before.st_dev, before.st_ino)
            _require(identity not in self.identities, 'producer_duplicate_file_identity')
            self.identities.add(identity)
            _require(before.st_size <= maximum and self.total + before.st_size <= MAX_TOTAL_BYTES, 'producer_byte_limit')
            chunks = []; size = 0
            while True:
                chunk = os.read(fd, min(65536, maximum + 1 - size))
                if not chunk: break
                chunks.append(chunk); size += len(chunk)
                _require(size <= maximum and self.total + size <= MAX_TOTAL_BYTES, 'producer_byte_limit')
            after = os.fstat(fd)
            observed = os.stat(target, follow_symlinks=False)
            _require(_identity(before) == _identity(after) == _identity(observed)
                     and size == before.st_size, 'producer_file_changed')
            for part in (target, *target.parents):
                _require(not part.is_symlink() and not getattr(part, 'is_junction', lambda: False)(), 'producer_link_refused')
        finally:
            os.close(fd)
        raw = b''.join(chunks)
        self.total += size
        self.files.append({'path': relative, 'bytes': size, 'sha256': hashlib.sha256(raw).hexdigest()})
        return raw


def _receipt(value, producer):
    required = {'schema', 'product_id', 'run_id', 'started_at', 'finished_at', 'request_sha256',
                'pins_sha256', 'durable', 'input_origin', 'provider_called', 'target_code_executed',
                'state', 'execution_ok', 'gate_quality', 'artifacts', 'engine', 'scope'}
    optional = {'source_selection', 'replay_of', 'reserved_bytes', 'worker_sha256', 'recipe_sha256',
                'quality_state', 'reason_code', 'exit_code', 'timed_out', 'source_manifest_sha256',
                'source_snapshot_created', 'storage'}
    _keys(value, required, optional)
    _require(value['schema'] == 'skyom.business.run.v1' and value['product_id'] == producer, 'producer_schema_or_identity_mismatch')
    _require(type(value['run_id']) is str and RUN.fullmatch(value['run_id']) is not None, 'producer_run_id_invalid')
    for name in ('request_sha256', 'pins_sha256', 'worker_sha256', 'recipe_sha256', 'source_manifest_sha256'):
        if name in value: _sha(value[name])
    for name in ('durable', 'target_code_executed', 'execution_ok', 'timed_out', 'source_snapshot_created'):
        if name in value: _require(type(value[name]) is bool, 'producer_boolean_invalid')
    for name in ('provider_called', 'gate_quality'):
        _require(value[name] is None or type(value[name]) is bool, 'producer_nullable_boolean_invalid')
    _require(value['input_origin'] == 'user_supplied', 'producer_origin_invalid')
    _require(type(value['scope']) is str and 1 <= len(value['scope']) <= 2048, 'producer_scope_invalid')
    _require(value['engine'] is None or type(value['engine']) is dict, 'producer_engine_invalid')
    for name in ('source_selection', 'storage'):
        if name in value: _require(type(value[name]) is dict, 'producer_metadata_invalid')
    for name in ('reserved_bytes', 'exit_code'):
        if name in value: _require(type(value[name]) is int, 'producer_integer_invalid')
    if 'reserved_bytes' in value:
        _require(value['reserved_bytes'] >= 0, 'producer_reservation_invalid')
    for name in ('reason_code', 'replay_of'):
        if name in value: _require(value[name] is None or type(value[name]) is str, 'producer_text_invalid')
    if value.get('replay_of') is not None:
        _require(RUN.fullmatch(value['replay_of']) is not None, 'producer_replay_id_invalid')
    if 'quality_state' in value:
        expected = 'not_measured' if value['gate_quality'] is None else 'passed' if value['gate_quality'] else 'failed'
        _require(value['quality_state'] == expected, 'producer_quality_state_inconsistent')
    _require(value['execution_ok'] is True, 'producer_execution_incomplete')
    _require(value['state'] == ('quality_failed' if value['gate_quality'] is False else 'completed'), 'producer_state_inconsistent')
    _require(value.get('timed_out', False) is False and value.get('exit_code', 0) == 0, 'producer_execution_inconsistent')
    rows = value['artifacts']
    _require(type(rows) is list and 1 <= len(rows) <= 32, 'producer_artifacts_invalid')
    declared = {}
    for row in rows:
        _keys(row, {'id', 'bytes', 'sha256'})
        identifier = row['id']
        _require(type(identifier) is str and ID.fullmatch(identifier) is not None
                 and identifier not in declared, 'producer_duplicate_or_invalid_artifact_id')
        _require(type(row['bytes']) is int and 0 <= row['bytes'] <= MAX_ARTIFACT_BYTES, 'producer_artifact_size_invalid')
        _sha(row['sha256']); declared[identifier] = row
    _require('input' in declared and declared['input']['sha256'] == value['request_sha256'], 'producer_input_binding_mismatch')
    return declared


def verify_producer_bundle(bundle, *, root, candidate, clock=None):
    """Check all declared public run artifacts; absent metadata cannot be inferred.

    `passed` means only this optional consistency veto did not fire. It never
    authorizes publication or authenticates a producer, Git subject, or CI run.
    """
    now = (clock or (lambda: dt.datetime.now(dt.timezone.utc)))()
    _require(isinstance(now, dt.datetime) and now.tzinfo is not None, 'producer_clock_invalid')
    result = {'schema_version': 'shipcheck/producer-bundle-verification-v1', 'passed': False,
              'subject_binding': 'declared_only', 'authenticity_established': False,
              'publication_authorized': False, 'producer_executed_here': False,
              'native_engine_receipts_replayed': False,
              'verification_scope': 'complete_declared_public_artifact_inventory; source_snapshots_and_databases_not_checked',
              'verified_at': now.timestamp(), 'receipts': [], 'files': [], 'reason_code': None}
    reader = None
    try:
        bundle = loads_strict(canonical_json(bundle), max_bytes=MAX_RECEIPT_BYTES)
        _keys(bundle, {'schema_version', 'candidate', 'max_age_seconds', 'require_quality', 'receipts'})
        _require(bundle['schema_version'] == SCHEMA, 'producer_bundle_schema_invalid')
        expected = candidate if isinstance(candidate, Candidate) else Candidate.from_dict(candidate)
        _require(Candidate.from_dict(bundle['candidate']) == expected, 'producer_candidate_mismatch')
        age_limit = bundle['max_age_seconds']
        _require(type(age_limit) is int and 1 <= age_limit <= 604800, 'producer_age_limit_invalid')
        result['max_age_seconds'] = age_limit
        _require(type(bundle['require_quality']) is bool, 'producer_quality_policy_invalid')
        entries = bundle['receipts']
        _require(type(entries) is list and 1 <= len(entries) <= 16, 'producer_receipt_inventory_empty_or_large')
        reader = _Reader(root); seen_runs = set(); seen_digests = set()
        for entry in entries:
            _keys(entry, {'producer_id', 'candidate', 'receipt_path', 'receipt_sha256', 'artifacts'})
            producer = entry['producer_id']
            _require(type(producer) is str and producer in PRODUCERS, 'producer_unsupported')
            _require(Candidate.from_dict(entry['candidate']) == expected, 'producer_candidate_mismatch')
            claimed = _sha(entry['receipt_sha256'])
            _require(claimed not in seen_digests, 'producer_duplicate_receipt')
            seen_digests.add(claimed)
            raw = reader.read(entry['receipt_path'], MAX_RECEIPT_BYTES)
            _require(hashlib.sha256(raw).hexdigest() == claimed, 'producer_receipt_hash_mismatch')
            value = loads_strict(raw, max_bytes=MAX_RECEIPT_BYTES)
            declared = _receipt(value, producer)
            _require(value['run_id'] not in seen_runs, 'producer_duplicate_run')
            seen_runs.add(value['run_id'])
            started, finished = _number(value['started_at']), _number(value['finished_at'])
            _require(finished >= started, 'producer_time_reversed')
            _require(finished <= now.timestamp(), 'producer_time_future')
            _require(now.timestamp() - finished <= age_limit, 'producer_receipt_stale')
            if bundle['require_quality']:
                _require(value['gate_quality'] is not None, 'producer_quality_not_measured')
                _require(value['gate_quality'] is True, 'producer_quality_failed')
            mappings = entry['artifacts']
            _require(type(mappings) is list and len(mappings) == len(declared), 'producer_artifact_inventory_incomplete')
            by_id = {}
            for binding in mappings:
                _keys(binding, {'id', 'path'})
                identifier = binding['id']
                _require(type(identifier) is str and identifier in declared and identifier not in by_id, 'producer_artifact_id_unknown_or_duplicate')
                by_id[identifier] = binding['path']
            _require(set(by_id) == set(declared), 'producer_artifact_inventory_incomplete')
            for identifier, path in by_id.items():
                content = reader.read(path, MAX_ARTIFACT_BYTES)
                wanted = declared[identifier]
                _require(len(content) == wanted['bytes'] and hashlib.sha256(content).hexdigest() == wanted['sha256'], 'producer_artifact_mismatch')
            result['receipts'].append({'producer_id': producer, 'run_id': value['run_id'],
                'receipt_sha256': claimed, 'candidate_digest_declared': expected.digest,
                'started_at': started, 'finished_at': finished, 'age_seconds': now.timestamp() - finished,
                'execution_ok': value['execution_ok'], 'gate_quality': value['gate_quality'],
                'scope_declared': value['scope'], 'provider_called': value['provider_called'],
                'durable_declared': value['durable'], 'target_code_executed_declared': value['target_code_executed'],
                'artifact_count': len(declared), 'input_sha256': value['request_sha256']})
        result.update(passed=True, reason_code='producer_bundle_consistent')
    except (OSError, SecurityError, ValidationError, TypeError, ValueError, OverflowError) as exc:
        # Do not echo input content or OS messages (which may include paths).
        code = str(exc) if isinstance(exc, ValidationError) else ''
        result['reason_code'] = code if re.fullmatch(r'producer_[a-z_]+', code) else 'producer_bundle_invalid_or_unreadable'
    if reader is not None:
        result['files'] = reader.files
        result['bytes_checked'] = reader.total
    result['verification_digest'] = object_digest(result)
    return result


def recheck_producer_files(proof, *, root, clock=None):
    """Before completing the workflow, detect changes to every checked input."""
    reader = _Reader(root)
    for item in proof['files']:
        raw = reader.read(item['path'], MAX_ARTIFACT_BYTES)
        _require(len(raw) == item['bytes'] and hashlib.sha256(raw).hexdigest() == item['sha256'], 'producer_file_changed_after_verification')
    now = (clock or (lambda: dt.datetime.now(dt.timezone.utc)))().timestamp()
    for receipt in proof['receipts']:
        _require(receipt['finished_at'] <= now, 'producer_time_future')
        _require(now - receipt['finished_at'] <= proof['max_age_seconds'], 'producer_receipt_stale')
