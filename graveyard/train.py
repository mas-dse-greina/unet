# Usage: numactl -p 1 python train.py 50 5 30
# numactl -m 1 python train.py --num_threads=34 --num_intra_threads=1 --blocktime=0

import argparse
parser = argparse.ArgumentParser()


parser.add_argument("--num_threads", type=int, default=34, help="the number of threads")
parser.add_argument("--num_intra_threads", type=int, default=2, help="the number of intraop threads")
parser.add_argument("--blocktime", type=int, default=30, help="blocktime")
parser.add_argument("--use_upsampling", action="store_true", default=False)

args = parser.parse_args()

import os


num_threads = args.num_threads
num_intra_op_threads = args.num_intra_threads

if (args.blocktime > 1000):
	blocktime = 'infinite'
else:
	blocktime = str(args.blocktime)

os.environ["KMP_BLOCKTIME"] = blocktime
os.environ["KMP_AFFINITY"]="granularity=thread,compact,1,0"
#os.environ['KMP_AFFINITY']='scatter,granularity=fine'

os.environ["OMP_NUM_THREADS"]= str(num_threads)
# os.environ["TF_ADJUST_HUE_FUSED"] = '1'
# os.environ['TF_ADJUST_SATURATION_FUSED'] = '1'
# os.environ['MKL_VERBOSE'] = '1'
# os.environ['MKL_DYNAMIC']='1'

os.environ['TF_CPP_MIN_LOG_LEVEL']='2'  # Get rid of the AVX, SSE warnings

# os.environ['MIC_ENV_PREFIX'] = 'PHI'
# os.environ['PHI_KMP_AFFINITY'] = 'compact'
# os.environ['PHI_KMP_PLACE_THREADS'] = '60c,3t'
# os.environ['PHI_OMP_NUM_THREADS'] = str(num_threads)

os.environ['TF_ENABLE_WINOGRAD_NONFUSED'] = '1'
os.environ['TF_AUTOTUNE_THRESHOLD'] = '1'

os.environ['MKL_NUM_THREADS'] =str(num_threads)
# os.environ['GOTO_NUM_THREADS'] = str(num_threads)

os.environ['KMP_SETTINGS'] = '1'  # Show the settins at runtime

# The timeline trace for TF is saved to this file.
# To view it, run this python script, then load the json file by 
# starting Google Chrome browser and pointing the URI to chrome://trace
# There should be a button at the top left of the graph where
# you can load in this json file.
timeline_filename = 'timeline_ge_unet_{}_{}_{}.json'.format(blocktime, num_threads, num_intra_op_threads)

import time

import tensorflow as tf

# configuration session
sess = tf.Session(config=tf.ConfigProto(
       intra_op_parallelism_threads=num_threads, inter_op_parallelism_threads=num_intra_op_threads))

run_options = tf.RunOptions(trace_level=tf.RunOptions.FULL_TRACE)
run_metadata = tf.RunMetadata()


from keras import backend as K

CHANNEL_LAST = True
if CHANNEL_LAST:
	concat_axis = -1
	data_format = 'channels_last'
	K.set_image_dim_ordering('tf')	
else:
	concat_axis = 1
	data_format = 'channels_first'
	K.set_image_dim_ordering('th')	

from keras.callbacks import ModelCheckpoint,TensorBoard
from keras.callbacks import History 
from keras.models import Model

from keras.layers import Input, Conv2D, Conv2DTranspose, MaxPooling2D, UpSampling2D, Dropout, concatenate
#from keras.layers import Convolution3D, MaxPooling3D, UpSampling3D
#from keras.layers import core
from keras.optimizers import Adam

import numpy as np

#from preprocess import * 
#from helper import *
import settings

def dice_coef(y_true, y_pred, smooth = 1e-7 ):
	y_true_f = K.flatten(y_true)
	y_pred_f = K.flatten(y_pred)
	intersection = K.sum(y_true_f * y_pred_f)
	coef = (2. * intersection + smooth) / (K.sum(y_true_f) + K.sum(y_pred_f) + smooth)
	return coef

def dice_coef_loss(y_true, y_pred):
	return -K.log(dice_coef(y_true, y_pred))


def model5_MultiLayer(weights=False, 
	filepath="", 
	img_rows = 224, 
	img_cols = 224, 
	n_cl_in=3,
	n_cl_out=3, 
	dropout=0.2, 
	learning_rate = 0.001,
	print_summary = False):
	""" difference from model: img_rows and cols, order of axis, and concat_axis"""

	if CHANNEL_LAST:
		inputs = Input((img_rows, img_cols, n_cl_in), name='Images')
	else:
		inputs = Input((n_cl_in, img_rows, img_cols), name='Images')

	conv1 = Conv2D(kernel_initializer='glorot_uniform', name='conv1a', filters=32, kernel_size=(3, 3), activation='relu', padding='same', data_format=data_format)(inputs)
	conv1 = Conv2D(kernel_initializer='glorot_uniform', name='conv1b', filters=32, kernel_size=(3, 3), activation='relu', padding='same', data_format=data_format)(conv1)
	pool1 = MaxPooling2D(name='pool1', pool_size=(2, 2), data_format=data_format)(conv1)

	conv2 = Conv2D(kernel_initializer='glorot_uniform', name='conv2a', filters=64, kernel_size=(3, 3), activation='relu', padding='same', data_format=data_format)(pool1)
	conv2 = Conv2D(kernel_initializer='glorot_uniform', name='conv2b', filters=64, kernel_size=(3, 3), activation='relu', padding='same', data_format=data_format)(conv2)
	pool2 = MaxPooling2D(pool_size=(2, 2), data_format=data_format)(conv2)

	conv3 = Conv2D(kernel_initializer='glorot_uniform', name='conv3a', filters=128, kernel_size=(3, 3), activation='relu', padding='same', data_format=data_format)(pool2)
	conv3 = Conv2D(name='conv3b', filters=128, kernel_size=(3, 3), activation='relu', padding='same', data_format=data_format)(conv3)
	pool3 = MaxPooling2D(pool_size=(2, 2), data_format=data_format)(conv3)

	conv4 = Conv2D(kernel_initializer='glorot_uniform', name='conv4a', filters=256, kernel_size=(3, 3), activation='relu', padding='same', data_format=data_format )(pool3)
	conv4 = Conv2D(name='conv4b', filters=256, kernel_size=(3, 3), activation='relu', padding='same', data_format=data_format )(conv4)
	pool4 = MaxPooling2D(pool_size=(2, 2), data_format=data_format)(conv4)

	conv5 = Conv2D(kernel_initializer='glorot_uniform', name='conv5a', filters=512, kernel_size=(3, 3), activation='relu', padding='same', data_format=data_format )(pool4)
	conv5 = Conv2D(kernel_initializer='glorot_uniform', name='conv5b', filters=512, kernel_size=(3, 3), activation='relu', padding='same', data_format=data_format )(conv5)

	if args.use_upsampling:
		up6 = concatenate([UpSampling2D(name='up6', size=(2, 2))(conv5), conv4], axis=concat_axis)
	else:
		up6 = concatenate([Conv2DTranspose(kernel_initializer='glorot_uniform', name='transConv6', filters=256, kernel_size=(2, 2), strides=(2, 2), padding='same')(conv5), conv4], axis=concat_axis)

	conv6 = Conv2D(name='conv6a', filters=256, kernel_size=(3, 3), activation='relu', padding='same', data_format=data_format)(up6)
	conv6 = Conv2D(name='conv6b', filters=256, kernel_size=(3, 3), activation='relu', padding='same', data_format=data_format)(conv6)

	if args.use_upsampling:
		up7 = concatenate([UpSampling2D(name='up7', size=(2, 2))(conv6), conv3], axis=concat_axis)
	else:
		up7 = concatenate([Conv2DTranspose(kernel_initializer='glorot_uniform', name='transConv7', filters=128, kernel_size=(2, 2), strides=(2, 2), padding='same')(conv6), conv3], axis=concat_axis)

	conv7 = Conv2D(kernel_initializer='glorot_uniform', name='conv7a', filters=128, kernel_size=(3, 3), activation='relu', padding='same', data_format=data_format)(up7)
	conv7 = Conv2D(kernel_initializer='glorot_uniform', name='conv7b', filters=128, kernel_size=(3, 3), activation='relu', padding='same', data_format=data_format)(conv7)

 	if args.use_upsampling:
		up8 = concatenate([UpSampling2D(name='up8', size=(2, 2))(conv7), conv2], axis=-1)
	else:
		up8 = concatenate([Conv2DTranspose(kernel_initializer='glorot_uniform', name='transConv8', filters=64, kernel_size=(2, 2), strides=(2, 2), padding='same')(conv7), conv2], axis=concat_axis)

	conv8 = Conv2D(kernel_initializer='glorot_uniform', name='conv8a', filters=64, kernel_size=(3, 3), activation='relu', padding='same', data_format=data_format)(up8)
	conv8 = Dropout(dropout)(conv8)
	conv8 = Conv2D(kernel_initializer='glorot_uniform', name='conv8b', filters=64, kernel_size=(3, 3), activation='relu', padding='same', data_format=data_format)(conv8)
	
	if args.use_upsampling:
		up9 = concatenate([UpSampling2D(name='up9', size=(2, 2))(conv8), conv1], axis=-1)
	else:
		up9 = concatenate([Conv2DTranspose(kernel_initializer='glorot_uniform', name='transConv9', filters=32, kernel_size=(2, 2), strides=(2, 2), padding='same')(conv8), conv1], axis=concat_axis)

	conv9 = Conv2D(kernel_initializer='glorot_uniform', name='conv9a', filters=32, kernel_size=(3, 3), activation='relu', padding='same', data_format=data_format)(up9)
	conv9 = Dropout(dropout)(conv9)
	conv9 = Conv2D(kernel_initializer='glorot_uniform', name='conv9b', filters=32, kernel_size=(3, 3), activation='relu', padding='same', data_format=data_format)(conv9)

	conv10 = Conv2D(kernel_initializer='glorot_uniform', name='conv10', filters=n_cl_out, kernel_size=(1, 1), activation='sigmoid', data_format=data_format)(conv9)
	model = Model(inputs=[inputs], outputs=[conv10])
	
	
	model.compile(optimizer=Adam(lr=learning_rate),
		loss='binary_crossentropy', #'binary_crossentropy', #dice_coef_loss,
		metrics=['accuracy', dice_coef], options=run_options, run_metadata=run_metadata)

	# if weights and len(filepath)>0:
	# 	model.load_weights(filepath)

	if print_summary:
		print (model.summary())	

	return model

def load_data(data_path, prefix = "_train"):
	imgs_train = np.load(os.path.join(data_path, 'imgs'+prefix+'.npy'), mmap_mode='r', allow_pickle=False)
	msks_train = np.load(os.path.join(data_path, 'msks'+prefix+'.npy'), mmap_mode='r', allow_pickle=False)

	return imgs_train, msks_train

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


	if not CHANNEL_LAST:
		new_imgs = np.transpose(new_imgs, [0,3,1,2])
		new_msks = np.transpose(new_msks, [0,3,1,2])

	return new_imgs, new_msks

def train_and_predict(data_path, img_rows, img_cols, n_epoch, input_no  = 3, output_no = 3,
	fn= "model", mode = 1):
	
	last_time = time.time()

	K.set_session(sess)
	
	print('Time elapsed to start session = {} seconds'.format(time.time() - last_time))
	last_time = time.time()

	print('-'*30)
	print('Loading and preprocessing train data...')
	print('-'*30)
	imgs_train, msks_train = load_data(data_path,"_train")
	imgs_train, msks_train = update_channels(imgs_train, msks_train, input_no, output_no, 
		mode)

	print('Shape train = {}'.format(imgs_train.shape))
	print('Time elapsed for training data loading = {} seconds'.format(time.time() - last_time))
	last_time = time.time()
	
	print('-'*30)
	print('Loading and preprocessing test data...')
	print('-'*30)
	imgs_test, msks_test = load_data(data_path,"_test")
	imgs_test, msks_test = update_channels(imgs_test, msks_test, input_no, output_no, mode)
	print('Shape test = {}'.format(imgs_test.shape))

	print('Time elapsed for test data loading = {} seconds'.format(time.time() - last_time))
	last_time = time.time()

	print('-'*30)
	print('Creating and compiling model...')
	print('-'*30)
	model		= model5_MultiLayer(False, False, img_rows, img_cols, input_no,	output_no)
	model_fn	= os.path.join(data_path, fn+'_{epoch:03d}.hdf5')
	print ("Writing model to ", model_fn)

	model_checkpoint = ModelCheckpoint(model_fn, monitor='loss', save_best_only=False) 
	#saves all models when set to False


	print('Time elapsed for model compiling = {} seconds'.format(time.time() - last_time))
	last_time = time.time()

	print('-'*30)
	print('Fitting model...')
	print('-'*30)
	print('Batch size = {}'.format(settings.BATCH_SIZE))
	history = History()
	history = model.fit(imgs_train, msks_train, 
		batch_size=settings.BATCH_SIZE, 
		epochs=n_epoch, 
		validation_data = (imgs_test, msks_test),
		verbose=1, 
	 	callbacks=[model_checkpoint, TensorBoard(log_dir='./keras_tb_logs', write_graph=True, write_images=True)])               #model_checkpoint])

	print('Time elapsed for model training = {} seconds'.format(time.time() - last_time))
	last_time = time.time()

	'''
	Save the training timeline
	'''
	from tensorflow.python.client import timeline

	fetched_timeline = timeline.Timeline(run_metadata.step_stats)
	chrome_trace = fetched_timeline.generate_chrome_trace_format()
	with open(timeline_filename, 'w') as f:
	    f.write(chrome_trace)


	json_fn = os.path.join(data_path, fn+'.json')
	with open(json_fn,'w') as f:
		f.write(model.to_json())


	# # print('-'*30)
	# # print('Loading saved weights...')
	# # print('-'*30)
	# epochNo = len(history.history['loss'])-1
	# model_fn	= os.path.join(data_path, '{}_{:03d}.hdf5'.format(fn, epochNo))
	# model.load_weights(model_fn)

	# print('Time elapsed for model save/load to disk = {} seconds'.format(time.time() - last_time))
	# last_time = time.time()

	# # print('-'*30)
	# # print('Predicting masks on test data...')
	# # print('-'*30)
	# msks_pred = model.predict(imgs_test, verbose=1)
	# # print("Done ", epochNo, np.min(msks_pred), np.max(msks_pred))
	# np.save(os.path.join(data_path, 'msks_pred.npy'), msks_pred)

	# scores = model.evaluate(imgs_test, msks_test, batch_size=128, verbose = 2)
	# print ("Evaluation Scores", scores)

	# print('Time elapsed for model evaluation = {} seconds'.format(time.time() - last_time))
	# last_time = time.time()

if __name__ =="__main__":

	start_time = time.time()

	train_and_predict(settings.OUT_PATH, settings.IMG_ROWS/settings.RESCALE_FACTOR, 
		settings.IMG_COLS/settings.RESCALE_FACTOR, 
		settings.EPOCHS, settings.IN_CHANNEL_NO, \
		settings.OUT_CHANNEL_NO, settings.MODEL_FN, settings.MODE)

	print('Total Time elapsed for entire script = {} seconds'.format(time.time() - start_time))
