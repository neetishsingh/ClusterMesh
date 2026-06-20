from enum import Enum, auto


class NodeState(Enum):
    HEALTHY = auto()
    SUSPECTED = auto()
    DEAD = auto()
    PREEMPTED = auto()
    OFFLINE = auto()


class ResourcePool(Enum):
    CPU = "cpu"
    MEMORY = "memory"
    GPU = "gpu"
    NIGHT = "night"


class TaskState(Enum):
    PENDING = auto()
    RUNNING = auto()
    CHECKPOINTING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    FAILED = auto()
    MIGRATING = auto()
