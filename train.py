# '''
# BEGIN - Limit Tensoflow to only use specific GPU
# '''
# import os

# gpu_num = 0

# os.environ['CUDA_DEVICE_ORDER'] = 'PCI_BUS_ID'   # see issue #152
# os.environ['CUDA_VISIBLE_DEVICES'] = '{}'.format(gpu_num)
# os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' # Supress Tensforflow debug messages

# import tensorflow as tf

# import time

# '''
# END - Limit Tensoflow to only use specific GPU
# '''

# numactl -p 1 python train.py --num_threads=50 --num_intra_threads=5 --batch_size=256 --blocktime=0
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--use_upsampling', help='use upsampling instead of transposed convolution',
					action='store_true', default=False)
parser.add_argument("--num_threads", type=int, default=34, help="the number of threads")
parser.add_argument("--num_intra_threads", type=int, default=1, help="the number of intraop threads")
parser.add_argument("--batch_size", type=int, default=512, help="the batch size for training")
parser.add_argument("--blocktime", type=int, default=30, help="blocktime")

args = parser.parse_args()

batch_size = args.batch_size

import os

num_threads = args.num_threads
num_intra_op_threads = args.num_intra_threads

if (args.blocktime > 1000):
	blocktime = 'infinite'
else:
	blocktime = str(args.blocktime)

os.environ['TF_CPP_MIN_LOG_LEVEL']='2'  # Get rid of the AVX, SSE warnings

os.environ["KMP_BLOCKTIME"] = blocktime
os.environ["KMP_AFFINITY"]="granularity=thread,compact,1,0"
os.environ["OMP_NUM_THREADS"]= str(num_threads)
os.environ["TF_ADJUST_HUE_FUSED"] = '1'
os.environ['TF_ADJUST_SATURATION_FUSED'] = '1'
os.environ['MKL_VERBOSE'] = '1'
os.environ['MKL_DYNAMIC']='1'

# os.environ['MIC_ENV_PREFIX'] = 'PHI'
# os.environ['PHI_KMP_AFFINITY'] = 'compact'
# os.environ['PHI_KMP_PLACE_THREADS'] = '60c,3t'
# os.environ['PHI_OMP_NUM_THREADS'] = str(num_threads)

os.environ['TF_ENABLE_WINOGRAD_NONFUSED'] = '1'
os.environ['TF_AUTOTUNE_THRESHOLD'] = '1'

os.environ['MKL_NUM_THREADS'] =str(num_threads)

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
# sess = tf.Session(config=tf.ConfigProto(
# 	   intra_op_parallelism_threads=num_threads, inter_op_parallelism_threads=num_intra_op_threads))

# config = tf.ConfigProto(device_count={"CPU": 16},
#                         intra_op_parallelism_threads=num_threads, inter_op_parallelism_threads=num_intra_op_threads)

config = tf.ConfigProto(intra_op_parallelism_threads=num_threads, inter_op_parallelism_threads=num_intra_op_threads)

config.graph_options.optimizer_options.opt_level = -1

sess = tf.Session(config=config)

run_options = tf.RunOptions(trace_level=tf.RunOptions.FULL_TRACE)
run_metadata = tf.RunMetadata()  # For Tensorflow trace

from keras import backend as K
K.set_image_dim_ordering('tf')	
from keras.callbacks import ModelCheckpoint, TensorBoard
from keras.callbacks import History 
from keras.models import Model

import numpy as np
import os

from preprocess import * 
from helper import *
import settings


def train_and_predict(data_path, img_rows, img_cols, n_epoch, input_no  = 3, output_no = 3,
	fn= "model", mode = 1, args=None):
	
	print('-'*30)
	print('Loading and preprocessing train data...')
	print('-'*30)
	imgs_train, msks_train = load_data(data_path,"_train")
	imgs_train, msks_train = update_channels(imgs_train, msks_train, input_no, output_no, 
		mode)
	
	print('-'*30)
	print('Loading and preprocessing test data...')
	print('-'*30)
	imgs_test, msks_test = load_data(data_path,"_test")
	imgs_test, msks_test = update_channels(imgs_test, msks_test, input_no, output_no, mode)


	print('-'*30)
	print('Creating and compiling model...')
	print('-'*30)

	

	model = model5_MultiLayer(args, False, False, img_rows, img_cols, input_no, output_no)
	model_fn	= os.path.join(data_path, fn+'_{epoch:03d}.hdf5')
	print ("Writing model to ", model_fn)

	model_checkpoint = ModelCheckpoint(model_fn, monitor='loss', save_best_only=False) 
	tensorboard_checkpoint = TensorBoard(log_dir='./keras_tensorboard', write_graph=True, write_images=True)
	

	print('-'*30)
	print('Fitting model...')
	print('-'*30)
	history = History()

	print('Batch size = {}'.format(batch_size))

	history = model.fit(imgs_train, msks_train, 
		batch_size=batch_size, 
		epochs=n_epoch, 
		validation_data = (imgs_test, msks_test),
		verbose=1, 
		callbacks=[model_checkpoint, tensorboard_checkpoint])

	json_fn = os.path.join(data_path, fn+'.json')
	with open(json_fn,'w') as f:
		f.write(model.to_json())


	'''
	Save the training timeline
	'''
	from tensorflow.python.client import timeline

	fetched_timeline = timeline.Timeline(run_metadata.step_stats)
	chrome_trace = fetched_timeline.generate_chrome_trace_format()
	with open(timeline_filename, 'w') as f:
		print('Saved Tensorflow trace to: {}'.format(timeline_filename))
		f.write(chrome_trace)

	print('-'*30)
	print('Loading saved weights...')
	print('-'*30)
	epochNo = len(history.history['loss'])-1
	model_fn	= os.path.join(data_path, '{}_{:03d}.hdf5'.format(fn, epochNo))
	model.load_weights(model_fn)

	print('-'*30)
	print('Predicting masks on test data...')
	print('-'*30)
	msks_pred = model.predict(imgs_test, verbose=1)
	
	#np.save(os.path.join(data_path, 'msks_pred.npy'), msks_pred)

	print('Saving predictions to file')
	np.save('msks_pred.npy', msks_pred)

	print('Evaluating model')
	scores = model.evaluate(imgs_test, msks_test, batch_size=batch_size, verbose = 2)
	print ("Evaluation Scores", scores)

if __name__ =="__main__":

	import datetime
	print(datetime.datetime.now())
	
	start_time = time.time()

	train_and_predict(settings.OUT_PATH, settings.IMG_ROWS/settings.RESCALE_FACTOR, 
		settings.IMG_COLS/settings.RESCALE_FACTOR, 
		settings.EPOCHS, settings.IN_CHANNEL_NO, \
		settings.OUT_CHANNEL_NO, settings.MODEL_FN, settings.MODE, args)

	print('Total time elapsed for program = {} seconds'.format(time.time() - start_time))
	print(datetime.datetime.now())



