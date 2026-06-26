# Data

Do not commit raw teleoperation data to the public repository.

Recommended local structure:

```text
data/
├─ raw/          # private raw demonstrations, ignored by Git
├─ processed/    # private converted samples, ignored by Git
└─ sample/       # tiny anonymized examples only, if allowed
```

A training sample can contain:

- visual observation metadata
- robot states
- end-effector poses
- hand states
- language instruction
- expert action chunk
