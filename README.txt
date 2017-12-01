# UNet

UNet architecture for Multimodal Brain Tumor Segmentation, built in TensorFlow 1.4.0 and optimized for single and multi-node execution in TensorFlow on Intel KNL servers.

## Getting Started

First things first, branches:

	Synchronous: Multi-node CPU implementation for synchronous weight updates (actively maintained)

	Asynchronous: Multi-node CPU implementation for asynchronous weight updates (functional, but not actively maintained)

	Master: Single node operation (functional, but not maintained in this fork)

## Requirements

Intel optimized TensorFlow 1.4.0, install instructions can be found at https://software.intel.com/en-us/articles/intel-optimized-tensorflow-wheel-now-available

Additional python packages required:

```
SimpleITK
opencv-python
h5py
shutil
tqdm
```

