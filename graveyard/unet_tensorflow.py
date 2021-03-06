#!/usr/bin/env python
''' 
----------------------------------------------------------------------------
Copyright 2017 Intel Nervana 
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
----------------------------------------------------------------------------
''' 

'''
  UNET entirely written in Tensorflow

  Test program to evaluate if MKL is being used for UNet.
  
  It should also produce a Tensorflow timeline showing
  the execution trace. 

  Usage:  numactl -p 1 python unet_tensorflow.py

'''

# The timeline trace for TF is saved to this file.
# To view it, run this python script, then load the json file by 
# starting Google Chrome browser and pointing the URI to chrome://trace
# There should be a button at the top left of the graph where
# you can load in this json file.
timeline_filename = 'tf_timeline_unet.json'

# The model will be saved to this file
savedModelWeightsFileName = 'savedModels/unet_model_weights_ge.ckpt'
USE_SAVED_MODEL = True  # Start training by loading in a previously trained model

import os

omp_threads = 68 # 50
intra_threads = 68 # 5 
os.environ["KMP_BLOCKTIME"] = "0" # 0
os.environ["KMP_AFFINITY"]="granularity=thread,compact,duplicates,0,0"
os.environ["OMP_NUM_THREADS"]= str(omp_threads)
os.environ['MKL_VERBOSE'] = '1'
#os.environ['KMP_SETTINGS'] = '1'

os.environ["TF_ADJUST_HUE_FUSED"] = '1'
os.environ['TF_ADJUST_SATURATION_FUSED'] = '1'
os.environ['TF_CPP_MIN_LOG_LEVEL']='2'  # Get rid of the AVX, SSE warnings

#os.environ['MKL_DYNAMIC']='1'

import tensorflow as tf
import numpy as np
from tqdm import tqdm  # pip install tqdm
from tensorflow.python.client import timeline

batch_size = 1024
training_epochs = 15
display_step = 1

BASE = "/home/bduser/tensorflow/GE/step1_train_model/Data/"
OUT_PATH  = BASE+"Data-Large/"
IN_CHANNEL_NO = 1
OUT_CHANNEL_NO = 1


MODEL_FN = "brainWholeTumor" #Name for Mode=1
#MODEL_FN = "brainActiveTumor" #Name for Mode=2
#MODEL_FN = "brainCoreTumor" #Name for Mode=3

#Use flair to identify the entire tumor: test reaches 0.78-0.80: MODE=1
#Use T1 Post to identify the active tumor: test reaches 0.65-0.75: MODE=2
#Use T2 to identify the active core (necrosis, enhancing, non-enh): test reaches 0.5-0.55: MODE=3
MODE=1

imgs_file_train = np.load(OUT_PATH + 'imgs_train.npy')
msks_file_train = np.load(OUT_PATH + 'msks_train.npy')

imgs_file_test = np.load(OUT_PATH + 'imgs_test.npy')
msks_file_test = np.load(OUT_PATH + 'msks_test.npy')

def update_channels(imgs, msks, input_no=3, output_no=3, mode=1):
	"""
	changes the order or which channels are used to allow full testing. Uses both
	Imgs and msks as input since different things may be done to both
	---
	mode: int between 1-3
	"""

	shp = imgs.shape
	new_imgs = np.zeros((shp[0],shp[1],shp[2],input_no))
	new_msks = np.zeros((shp[0],shp[1],shp[2],output_no))

	if mode==1:
		new_imgs[:,:,:,0] = imgs[:,:,:,2] # flair
		new_msks[:,:,:,0] = msks[:,:,:,0]+msks[:,:,:,1]+msks[:,:,:,2]+msks[:,:,:,3]
		# print('-'*10,' Whole tumor', '-'*10)
	elif mode == 2:
		#core (non enhancing)
		new_imgs[:,:,:,0] = imgs[:,:,:,0] # t1 post
		new_msks[:,:,:,0] = msks[:,:,:,3]
		# print('-'*10,' Predicing enhancing tumor', '-'*10)
	elif mode == 3:
		#core (non enhancing)
		new_imgs[:,:,:,0] = imgs[:,:,:,1]# t2 post
		new_msks[:,:,:,0] = msks[:,:,:,0]+msks[:,:,:,2]+msks[:,:,:,3]# active core
		# print('-'*10,' Predicing active Core', '-'*10)

	else:
		new_msks[:,:,:,0] = msks[:,:,:,0]+msks[:,:,:,1]+msks[:,:,:,2]+msks[:,:,:,3]

	return new_imgs[0:2048].astype(np.float32), new_msks[0:2048].astype(np.float32)

imgs_file_train, msks_file_train = update_channels(imgs_file_train, msks_file_train, IN_CHANNEL_NO, OUT_CHANNEL_NO, MODE)
imgs_file_test,  msks_file_test  = update_channels(imgs_file_test, msks_file_test, IN_CHANNEL_NO, OUT_CHANNEL_NO, MODE)


assert imgs_file_train.shape == msks_file_train.shape # Make sure images and masks are same size and count

img_height = imgs_file_train.shape[1]  # Needs to be an even number for max pooling to work
img_width = imgs_file_train.shape[2]   # Needs to be an even number for max pooling to work
n_channels = imgs_file_train.shape[3]
data_shape = (settings['batch_size'], img_height, img_width, n_channels)

imgs_placeholder = tf.placeholder(imgs_file_train.dtype, shape=data_shape)
msks_placeholder = tf.placeholder(msks_file_train.dtype, shape=data_shape)


def create_unet(imgs_placeholder):
    '''
    BEGIN 
    TF UNET IMPLEMENTATION
    '''

    conv1 = tf.layers.conv2d(name='conv1a', inputs=imgs_placeholder, filters=32, kernel_size=[3, 3], activation=tf.nn.relu, padding='SAME')
    conv1 = tf.layers.conv2d(name='conv1b', inputs=conv1, filters=32, kernel_size=[3, 3], activation=tf.nn.relu, padding='SAME')
    pool1 = tf.layers.max_pooling2d(name='pool1', inputs=conv1, pool_size=[2,2], strides=2) # img = 64 x 64 if original size was 128 x 128

    conv2 = tf.layers.conv2d(name='conv2a', inputs=pool1, filters=64, kernel_size=[3, 3], activation=tf.nn.relu, padding='SAME')
    conv2 = tf.layers.conv2d(name='conv2b', inputs=conv2, filters=64, kernel_size=[3, 3], activation=tf.nn.relu, padding='SAME')
    pool2 = tf.layers.max_pooling2d(name='pool2', inputs=conv2, pool_size=[2, 2], strides=2) # img = 32 x 32 if original size was 128 x 128

    conv3 = tf.layers.conv2d(name='conv3a', inputs=pool2, filters=128, kernel_size=[3, 3], activation=tf.nn.relu, padding='SAME')
    conv3 = tf.layers.conv2d(name='conv3b', inputs=conv3, filters=128, kernel_size=[3, 3], activation=tf.nn.relu, padding='SAME')
    pool3 = tf.layers.max_pooling2d(name='pool3', inputs=conv3, pool_size=[2, 2], strides=2) # img = 16 x 16 if original size was 128 x 128

    conv4 = tf.layers.conv2d(name='conv4a', inputs=pool3, filters=256, kernel_size=[3, 3], activation=tf.nn.relu, padding='SAME')
    conv4 = tf.layers.conv2d(name='conv4b', inputs=conv4, filters=256, kernel_size=[3, 3], activation=tf.nn.relu, padding='SAME')
    pool4 = tf.layers.max_pooling2d(name='pool4', inputs=conv4, pool_size=[2, 2], strides=2) #img = 8 x 8 if original size was 128 x 128

    conv5 = tf.layers.conv2d(name='conv5a', inputs=pool4, filters=512, kernel_size=[3, 3], activation=tf.nn.relu, padding='SAME')
    conv5 = tf.layers.conv2d(name='conv5b', inputs=conv5, filters=512, kernel_size=[3, 3], activation=tf.nn.relu, padding='SAME')

    up6 = tf.concat([tf.image.resize_nearest_neighbor(conv5, (img_height//8, img_width//8)), conv4], -1, name='up6')
    conv6 = tf.layers.conv2d(name='conv6a', inputs=up6, filters=256, kernel_size=[3,3], activation=tf.nn.relu, padding='SAME')
    conv6 = tf.layers.conv2d(name='conv6b', inputs=conv6, filters=256, kernel_size=[3,3], activation=tf.nn.relu, padding='SAME')

    up7 = tf.concat([tf.image.resize_nearest_neighbor(conv6, (img_height//4, img_width//4)), conv3], -1, name='up7')
    conv7 = tf.layers.conv2d(name='conv7a', inputs=up7, filters=128, kernel_size=[3, 3], activation=tf.nn.relu, padding='SAME')
    conv7 = tf.layers.conv2d(name='conv7b', inputs=conv7, filters=128, kernel_size=[3,3], activation=tf.nn.relu, padding='SAME')

    up8 = tf.concat([tf.image.resize_nearest_neighbor(conv7, (img_height//2, img_width//2)), conv2], -1, name='up8')
    conv8 = tf.layers.conv2d(name='conv8a', inputs=up8, filters=64, kernel_size=[3, 3], activation=tf.nn.relu, padding='SAME')
    conv8 = tf.nn.dropout(conv8, 0.5)
    conv8 = tf.layers.conv2d(name='conv8b', inputs=conv8, filters=64, kernel_size=[3, 3], activation=tf.nn.relu, padding='SAME')

    up9 = tf.concat([tf.image.resize_nearest_neighbor(conv8, (img_height, img_width)), conv1], -1, name='up9')
    conv9 = tf.layers.conv2d(name='conv9a', inputs=up9, filters=32, kernel_size=[3, 3], activation=tf.nn.relu, padding='SAME')
    conv9 = tf.nn.dropout(conv9, 0.5)
    conv9 = tf.layers.conv2d(name='conv9b', inputs=conv9, filters=32, kernel_size=[3, 3], activation=tf.nn.relu, padding='SAME')

    pred_msk = tf.layers.conv2d(name='prediction_mask_loss', inputs=conv9, filters=1, kernel_size=[1,1], activation=None, padding='SAME')

    out_msk = tf.nn.sigmoid(pred_msk)

    return pred_msk, out_msk

def dice_coefficient(y_pred, y_true):
    '''
    Returns Dice coefficient
    2 * intersection / (|area 1| + |area 2|)

    '''
    smoothing = 1e-7

    intersection = tf.reduce_sum(y_pred * y_true, axis=[1, 2, 3]) + smoothing
    
    # Sorensen Dice
    denominator = tf.reduce_sum(y_pred, axis=[1, 2, 3]) + tf.reduce_sum(y_true, axis=[1, 2, 3]) + smoothing

    # Jaccard Dice
    #denominator = tf.reduce_sum(y_pred*y_pred, axis=[1, 2, 3]) + tf.reduce_sum(y_true*y_true, axis=[1, 2, 3]) + smoothing

    return tf.reduce_mean(2. * intersection / denominator)


pred_msk, out_msk = create_unet(imgs_placeholder)

loss = tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits(labels=msks_placeholder, logits=pred_msk))
dice_cost = dice_coefficient(out_msk, msks_placeholder)

# train_step = tf.train.GradientDescentOptimizer(0.5).minimize(loss)

train_step = tf.train.AdamOptimizer().minimize(loss)

# Add ops to save and restore all the variables.
saver = tf.train.Saver()

# Initialize all variables
init_op = tf.global_variables_initializer()

options = tf.RunOptions(trace_level=tf.RunOptions.FULL_TRACE)
run_metadata = tf.RunMetadata()

sess = tf.Session(config=tf.ConfigProto(
        intra_op_parallelism_threads=omp_threads, inter_op_parallelism_threads=intra_threads))

sess.run(init_op, options=options, run_metadata=run_metadata)


# Initialize the variables 
init = tf.global_variables_initializer()

num_samples = imgs_file_train.shape[0]
print('Number of training samples = {}'.format(num_samples))
print('Number of testing samples = {}'.format(imgs_file_test.shape[0]))
print('Batch size = {}'.format(batch_size))

# Start training
with sess.as_default():

    '''
    Load the previously saved model file if it exists
    '''
    if USE_SAVED_MODEL:
        # Restore variables from disk.
        try:
            saver.restore(sess, savedModelWeightsFileName)
            print('Restoring weights from previously-saved file: {}'.format(savedModelWeightsFileName))
        except:
            sess.run(init)
    else:
        # Run the initializer
        sess.run(init)

    last_loss = float('inf') # Initialize to infinity
    
    # Fit all training data
    for epoch in range(training_epochs):

        for idx in tqdm(range(0, num_samples-batch_size, batch_size), desc='Epoch {} of {}'.format(epoch+1, training_epochs)):

            sess.run(train_step, feed_dict={imgs_placeholder: imgs_file_train[idx:(idx+batch_size)], msks_placeholder: msks_file_train[idx:(idx+batch_size)]})
            fetched_timeline = timeline.Timeline(run_metadata.step_stats)
            chrome_trace = fetched_timeline.generate_chrome_trace_format()
            with open(timeline_filename, 'w') as f:
                f.write(chrome_trace)
        	
        # Handle partial batches (if num_samples is not evenly divisible by batch_size)
        if (num_samples%batch_size) > 0:
        	sess.run(train_step, feed_dict={imgs_placeholder: imgs_file_train[idx:(idx+(num_samples%batch_size))], msks_placeholder: msks_file_train[idx:(idx+(num_samples%batch_size))]})
        	

        # Display logs per epoch step
        if (epoch+1) % display_step == 0:
            
            loss_test, dice_test = sess.run([loss, dice_cost], feed_dict={imgs_placeholder: imgs_file_test, msks_placeholder: msks_file_test})
            print('Epoch: {}, test loss = {:.6f}, Dice coefficient = {:.6f}'.format(epoch+1, loss_test, dice_test))

            '''
            Save the model if it is an improvement
            '''
            if loss_test < last_loss:
                last_loss = loss_test
                # Save the variables to disk.
                save_path = saver.save(sess, savedModelWeightsFileName)
                print('UNet Model weights saved in file: {}'.format(save_path))


    print('Training finished.')

    print('Predicting segmentation masks for test set')
    test_preds = sess.run(out_msk, feed_dict={imgs_placeholder: imgs_file_test})
    
    np.save('test_predictions.npy', test_preds)
    print('Test set segmentation masks saved to test_predictions.npy')


	

