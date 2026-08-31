"""Compatibility shim for a legacy Render build command.

The public Render service intentionally uses the lightweight YAMNet fallback.
PANNs/CNN14 remains installed only on the Pi 5/local hub, where its PyTorch
runtime and checkpoint can be provisioned.  Some existing Render services have
the former checkpoint-download command saved in their dashboard settings; this
no-op keeps those deployments successful until that setting is updated.
"""

print("Skipping PANN checkpoint download on Render; the cloud service uses YAMNet.")
