#!/bin/sh
# ----------------------------------------------------------------------------
# Copyright 2017 Intel
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ----------------------------------------------------------------------------

# Run the Ansible playbook to start the distribute tensorflow workers
# The playbook will first start the parameter server on the local machine.
# Then it will sync the files from the worker directories to this directory.
# It will then start the train_dist.py
# You can keep track of the training progress for each worker by
# logging into that server and looking at training.log file.
DIR_IN='/home/bduser/unet/unet/'
cd $DIR_IN
python create_inventory.py
echo 'Created new inventory file for Ansible based on settings.py'
ansible-playbook -i inv.yml -e dir_in=$DIR_IN distributed_train.yml


