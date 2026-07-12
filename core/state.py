# core/state.py
# Application state constants shared across core modules.
# INVARIANT: No platform-specific imports.

STATE_IDLE = "IDLE"
STATE_RECORDING = "RECORDING"
STATE_PROCESSING = "PROCESSING"
STATE_DONE = "DONE"
STATE_ERROR = "ERROR"
STATE_SYNTHESIS = "SYNTHESIS"
