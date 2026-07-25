"""The random source used for every game draw.

`random`'s default Mersenne Twister is reproducible: its full internal state can be
reconstructed from a run of observed outputs, after which every future draw is
predictable. In a social-deduction game the draw *is* the secret — who is the
undercover, which of the two words each side gets, where the assassin sits on the
Codenames board — so the game must not be dealt from a predictable stream.

`SystemRandom` reads the OS entropy source instead. It is slower per call, which is
irrelevant at the handful of draws a game start needs.

Import the shared instance rather than calling `random.*` directly, so there is one
place to look for "how does this project draw" (and one patch target in tests).
"""

import random

rng = random.SystemRandom()
