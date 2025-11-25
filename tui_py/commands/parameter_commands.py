"""
Parameter command definitions.
"""

from tau_lib.core.commands_api import (
    CommandDef, CommandParam, ParamType, CommandCategory,
    COMMAND_REGISTRY as registry
)


def register_parameter_commands(app_state):
    """Register parameter commands."""

    # ========== PARAMETER COMMANDS ==========

    registry.register(CommandDef(
        name="tau_a",
        category=CommandCategory.PARAMS,
        description_short="Set attack time constant",
        description_long="Controls rise time of envelope detector. Smaller = faster attack.",
        params=[
            CommandParam("tau", ParamType.FLOAT, "Time constant in seconds", min_val=0.0001, max_val=1.0)
        ],
        handler=lambda tau: setattr(app_state.kernel, 'tau_a', tau)
    ))

    registry.register(CommandDef(
        name="tau_r",
        category=CommandCategory.PARAMS,
        description_short="Set release time constant",
        description_long="Controls decay time of envelope detector. Smaller = faster release.",
        params=[
            CommandParam("tau", ParamType.FLOAT, "Time constant in seconds", min_val=0.0001, max_val=1.0)
        ],
        handler=lambda tau: setattr(app_state.kernel, 'tau_r', tau)
    ))

    registry.register(CommandDef(
        name="thr",
        category=CommandCategory.PARAMS,
        description_short="Set threshold",
        description_long="Detection threshold in sigma units. Higher = fewer detections.",
        aliases=["threshold"],
        params=[
            CommandParam("threshold", ParamType.FLOAT, "Threshold in sigma", min_val=0.5, max_val=20.0)
        ],
        handler=lambda thr: setattr(app_state.kernel, 'threshold', thr)
    ))

    registry.register(CommandDef(
        name="ref",
        category=CommandCategory.PARAMS,
        description_short="Set refractory period",
        description_long="Minimum time between detections. Prevents double-triggers.",
        aliases=["refractory"],
        params=[
            CommandParam("ref", ParamType.FLOAT, "Refractory period in seconds", min_val=0.001, max_val=1.0)
        ],
        handler=lambda ref: setattr(app_state.kernel, 'refractory', ref)
    ))

    registry.register(CommandDef(
        name="tau_a_semitone",
        category=CommandCategory.PARAMS,
        description_short="Adjust tau_a by musical semitones",
        description_long="±1 semitone = 2^(±1/12) frequency ratio. Useful for musical tuning.",
        params=[
            CommandParam("semitones", ParamType.INT, "Number of semitones (can be negative)", min_val=-24, max_val=24)
        ],
        key_binding="z/Z",
        handler=lambda st: _adjust_tau_semitone(app_state, 'tau_a', st)
    ))

    registry.register(CommandDef(
        name="tau_r_semitone",
        category=CommandCategory.PARAMS,
        description_short="Adjust tau_r by musical semitones",
        params=[
            CommandParam("semitones", ParamType.INT, "Number of semitones (can be negative)", min_val=-24, max_val=24)
        ],
        key_binding="x/X",
        handler=lambda st: _adjust_tau_semitone(app_state, 'tau_r', st)
    ))

