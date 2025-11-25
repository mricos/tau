"""Core modules: state, config, commands API."""
from .state import AppState, KernelParams, Transport, Channel, ChannelManager
from .config import load_config, save_config, get_default_config_path
from .commands_api import CommandDef, CommandCategory, CommandParam, ParamType, COMMAND_REGISTRY
