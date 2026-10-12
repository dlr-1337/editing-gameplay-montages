"""RIFE (AI frame interpolation) loader shared by prep / densify / repair / rife_compare.

The Python binding reads the network layout from the NAME of the model directory, so the path
must keep "rife-v4.25" (or whichever version) in it."""
import os, sys

DEFAULT = "rife-v4.25"          # best of seven versions on real gameplay triplets (see rife_compare.py)


def model_dir(name=DEFAULT):
    cands = [os.environ.get("RIFE_MODEL"), f"models/{name}", f"dl_rife_models/{name}",
             os.path.expanduser(f"~/.claude/skills/editing-gameplay-montages/models/{name}")]
    for c in cands:
        if c and os.path.exists(os.path.join(c, "flownet.bin")):
            return os.path.abspath(c)
    raise SystemExit(f"RIFE model {name} not found: copy the skill's models/ folder here or set RIFE_MODEL")


def load(name=DEFAULT):
    from rife_ncnn_vulkan_python import Rife
    return Rife(gpuid=int(os.environ.get("RIFE_GPU", "0")), model=model_dir(name), num_threads=2)    # RIFE_GPU: Vulkan device index


def finish():
    """Call as the very last statement of a script that loaded the model. The Vulkan runtime behind the
    binding crashes while the process unloads (segmentation fault, exit code 139) although all the work
    is done and written; this ends the process without running the unload handlers, with exit code 0."""
    sys.stdout.flush()
    sys.stderr.flush()
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        k.GetCurrentProcess.restype = ctypes.c_void_p
        k.TerminateProcess(ctypes.c_void_p(k.GetCurrentProcess()), 0)
    os._exit(0)


class Tween:
    """Interpolation that stays inside the linear zone of RIFE's time step.

    Measured on v4.25 (ncnn) in October 2026: for a time step below about 0.08 the network returns the first
    frame unchanged, above 0.92 the second one, and it only catches up by about 0.25 (steps between 0.25 and
    0.75 are linear). In a 16x grid that made the sub-frames 15/16, 0 and 1/16 identical: slow motion stalled
    for an eighth of a frame at every real frame. So a step outside 0.2..0.8 is done in two stages, through
    the 0.25 or 0.75 frame. tag = anything that identifies the pair (the two stage frames are cached per pair)."""

    def __init__(self, rife):
        self.rife, self.tag, self.q = rife, None, {}

    def __call__(self, a, b, t, tag=None):
        if 0.2 <= t <= 0.8:
            return self.rife.process_cv2(a, b, t)
        if tag is None or tag != self.tag:
            self.tag, self.q = tag, {}
        if t < 0.2:
            if "lo" not in self.q:
                self.q["lo"] = self.rife.process_cv2(a, b, 0.25)
            return self.rife.process_cv2(a, self.q["lo"], t / 0.25)
        if "hi" not in self.q:
            self.q["hi"] = self.rife.process_cv2(a, b, 0.75)
        return self.rife.process_cv2(self.q["hi"], b, (t - 0.75) / 0.25)
