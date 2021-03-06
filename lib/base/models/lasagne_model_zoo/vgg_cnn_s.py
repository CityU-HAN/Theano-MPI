import lasagne
from lasagne.layers import InputLayer
from lasagne.layers import DenseLayer,DropoutLayer
from lasagne.layers import ConcatLayer
from lasagne.layers import NonlinearityLayer
from lasagne.layers import GlobalPoolLayer
from lasagne.layers.dnn import Conv2DDNNLayer as ConvLayer
from lasagne.layers.dnn import MaxPool2DDNNLayer as PoolLayerDNN
from lasagne.layers import MaxPool2DLayer as PoolLayer
from lasagne.layers import LocalResponseNormalization2DLayer as LRNLayer
from lasagne.nonlinearities import softmax, linear


def build_model(input_shape):
    
    net = {}
    net['input'] = InputLayer(input_shape)
    net['conv1'] = ConvLayer(net['input'], num_filters=96, filter_size=7, stride=2, flip_filters=False)
    net['norm1'] = LRNLayer(net['conv1'], alpha=0.0001) # caffe has alpha = alpha * pool_size
    net['pool1'] = PoolLayer(net['norm1'], pool_size=3, stride=3, ignore_border=False)
    net['conv2'] = ConvLayer(net['pool1'], num_filters=256, filter_size=5, flip_filters=False)
    net['pool2'] = PoolLayer(net['conv2'], pool_size=2, stride=2, ignore_border=False)
    net['conv3'] = ConvLayer(net['pool2'], num_filters=512, filter_size=3, pad=1, flip_filters=False)
    net['conv4'] = ConvLayer(net['conv3'], num_filters=512, filter_size=3, pad=1, flip_filters=False)
    net['conv5'] = ConvLayer(net['conv4'], num_filters=512, filter_size=3, pad=1, flip_filters=False)
    net['pool5'] = PoolLayer(net['conv5'], pool_size=3, stride=3, ignore_border=False)
    net['fc6'] = DenseLayer(net['pool5'], num_units=4096)
    net['drop6'] = DropoutLayer(net['fc6'], p=0.5)
    net['fc7'] = DenseLayer(net['drop6'], num_units=4096)
    net['drop7'] = DropoutLayer(net['fc7'], p=0.5)
    net['fc8'] = DenseLayer(net['drop7'], num_units=1000, nonlinearity=lasagne.nonlinearities.softmax)
                                    
    for layer in net.values():
        print str(lasagne.layers.get_output_shape(layer))
        
    return net
    

import numpy as np
import theano
import theano.tensor as T
rng = np.random.RandomState(23455)

import sys
sys.path.append('../lib/base/models/')
from customized import Customized 

class VGGNet_16(Customized): # c01b input

    '''

    overwrite those methods in the Customized class


    '''
    
    def __init__(self,config): 
        
        self.config = config
        self.verbose = config['verbose']
        
        self.name = 'vggnet'
        
        # input shape in c01b 
        self.channels = 3 # 'c' mean(R,G,B) = (103.939, 116.779, 123.68)
        self.input_width = self.config['input_width'] # '0' single scale training 224
        self.input_height = self.config['input_height'] # '1' single scale training 224
        self.batch_size = self.config['batch_size'] # 'b'
        
        # output dimension
        self.n_softmax_out = self.config['n_softmax_out']
        
        
        
        # training related
        self.base_lr = np.float32(self.config['learning_rate'])
        self.shared_lr = theano.shared(self.base_lr)
        self.step_idx = 0
        self.mu = config['momentum'] # def: 0.9 # momentum
        self.eta = config['weight_decay'] #0.0002 # weight decay
        
        self.x = T.ftensor4('x')
        self.y = T.lvector('y')      
        
        self.shared_x = theano.shared(np.zeros((
                                                3,
                                                self.input_width, 
                                                self.input_height,
                                                self.config['file_batch_size']
                                                ), 
                                                dtype=theano.config.floatX),  
                                                borrow=True)
                                              
        self.shared_y = theano.shared(np.zeros((self.config['file_batch_size'],), 
                                          dtype=int),   borrow=True)
                                          
        # build model                                 
        net = self.build_model(input_shape=(self.batch_size, 3, self.input_width, self.input_height)) # bc01
        self.output_layer = net['fc8'] 
        
        from lasagne.layers import get_all_params
        self.params = lasagne.layers.get_all_params(self.output_layer, trainable=True)
        
        # test number 10
        del self.params[10]
        
        # count params
        self.count_params()
                                          
        # shared variable for storing momentum before exchanging momentum(delta w)
        self.vels = [theano.shared(param_i.get_value() * 0.)
            for param_i in self.params]
        
        # shared variable for accepting momentum during exchanging momentum(delta w)
        self.vels2 = [theano.shared(param_i.get_value() * 0.)
            for param_i in self.params]
                                          
        self.train = None
        self.val = None
        self.inference = None
        self.get_vel = None
        self.descent_vel = None
        
    def build_model(self, input_shape):
        
        if self.verbose: print 'VGGNet (from lasagne model zoo)'
        
        return build_model(input_shape)
        
    def count_params(self):
        
        size=0
        for param in self.params:
            
            size+=param.size.eval()
            
            print param.shape.eval()
            
        self.model_size = size
            
        print 'model size %d' % int(self.model_size)
                                          
        
    def errors(self, p_y_given_x, y):
        
        y_pred = T.argmax(p_y_given_x, axis=1)
        
        if y.ndim != y_pred.ndim:
            raise TypeError('y should have the same shape as self.y_pred',
                            ('y', y.type, 'y_pred', y_pred.type))
        # check if y is of the correct datatype
        if y.dtype.startswith('int'):
            # the T.neq operator returns a vector of 0s and 1s, where 1
            # represents a mistake in prediction
            return T.mean(T.neq(y_pred, y))
        else:
            raise NotImplementedError()

        
    def errors_top_x(self, p_y_given_x, y, num_top=5):                       
                                    
        if num_top != 5: print 'val errors from top %d' % num_top        
        
        # check if y is of the correct datatype
        if y.dtype.startswith('int'):
            # the T.neq operator returns a vector of 0s and 1s, where 1
            # represents a mistake in prediction
            y_pred_top_x = T.argsort(p_y_given_x, axis=1)[:, -num_top:]
            y_top_x = y.reshape((y.shape[0], 1)).repeat(num_top, axis=1)
            return T.mean(T.min(T.neq(y_pred_top_x, y_top_x), axis=1))
        else:
            raise NotImplementedError()             
        
    def compile_train(self):

        print 'compiling training function...'
        
        x = self.x
        y = self.y
        
        subb_ind = T.iscalar('subb')  # sub batch index
        shared_x = self.shared_x[:,:,:,subb_ind*self.batch_size:(subb_ind+1)*self.batch_size].dimshuffle(3, 0, 1, 2) # c01b to bc01
        shared_y=self.shared_y[subb_ind*self.batch_size:(subb_ind+1)*self.batch_size]
        
        # training
        from lasagne.layers import get_output
        prediction = lasagne.layers.get_output(self.output_layer, x, deterministic=False)
        loss = lasagne.objectives.categorical_crossentropy(prediction, y).mean()
        error = self.errors(prediction, y)

        # self.output = softmax_layer.p_y_given_x
        # self.cost = softmax_layer.negative_log_likelihood(y)+\
                # 0.3*aux1.negative_log_likelihood(y)+0.3*aux2.negative_log_likelihood(y)
                                          
        self.grads = T.grad(loss,self.params)

    
        # updates_w,updates_v,updates_dv = updates_dict(config, model,
        #                             use_momentum=config['use_momentum'],
        #                             use_nesterov_momentum=config['use_nesterov_momentum'])
        
        updates_w = lasagne.updates.nesterov_momentum(
                loss, self.params, learning_rate=self.shared_lr.get_value(), momentum=self.mu)
                
        if self.config['monitor_grad']:
            
            shared_grads = [theano.shared(param_i.get_value() * 0.) for param_i in self.params]
            updates_g = zip(shared_grads, self.grads)
            updates_w+=updates_g
            
            norms = [grad.norm(L=2) for grad in shared_grads]
            
            self.get_norm = theano.function([subb_ind], norms,
                                              givens=[(x, shared_x), 
                                                      (y, shared_y)]
                                                                          )
                                      

        self.train= theano.function([subb_ind], [loss,error], updates=updates_w,
                                              givens=[(x, shared_x), 
                                                      (y, shared_y)]
                                                                          )
                                                                          
        # self.get_vel= theano.function([subb_ind], [cost,error], updates=updates_v,
        #                                       givens=[(x, shared_x),
        #                                               (y, shared_y)]
        #                                                                   )
        #
        #
        # self.descent_vel = theano.function([],[],updates=updates_dv)
        
    def compile_inference(self):

        print 'compiling inference function...'
    
        x = self.x
        
        from lasagne.layers import get_output
        prediction = lasagne.layers.get_output(self.output_layer, x, deterministic=True)
    
        self.inference = theano.function([x],prediction)
        
    def compile_val(self):

        print 'compiling validation function...'
    
        x = self.x
        y = self.y
        
        subb_ind = T.iscalar('subb')  # sub batch index
        shared_x = self.shared_x[:,:,:,subb_ind*self.batch_size:(subb_ind+1)*self.batch_size].dimshuffle(3, 0, 1, 2) # c01b to bc01
        shared_y=self.shared_y[subb_ind*self.batch_size:(subb_ind+1)*self.batch_size]
            
        # validation
        from lasagne.layers import get_output
        prediction = lasagne.layers.get_output(self.output_layer, x, deterministic=True)
        loss = lasagne.objectives.categorical_crossentropy(prediction, y).mean()
        error = self.errors(prediction, y)
        error_top_5 = self.errors_top_x(prediction, y, num_top=5)
        
        self.val =  theano.function([subb_ind], [loss,error,error_top_5], updates=[], 
                                          givens=[(x, shared_x),
                                                  (y, shared_y)]
                                                                )
                                                                
    def set_dropout_off(self):
        
        '''
        no need to call this function, since it's taken care of in lasagne by specifying (deterministic=True)
        '''
        
        pass
    
    def set_dropout_on(self):
        '''
        no need to call this function, since it's taken care of in lasagne
        '''
        
        pass
                                                                                     
    def adjust_lr(self, epoch, size):
            
        '''
        borrowed from AlexNet
        '''
        # lr is calculated every time as a function of epoch and size
        
        if self.config['lr_policy'] == 'step':
            
            stp0,stp1,stp2 = self.config['lr_step']
            
            if epoch >=stp0 and epoch < stp1:

                self.step_idx = 1
        
            elif epoch >=stp1 and epoch < stp2:
                
                self.step_idx = 2

            elif epoch >=stp2 and epoch < self.config['n_epochs']:
                
                self.step_idx = 3
                
            else:
                pass
            
            tuned_base_lr = self.base_lr * 1.0/pow(10.0,self.step_idx) 
                
        if self.config['lr_policy'] == 'auto':
            if epoch>5 and (val_error_list[-3] - val_error_list[-1] <
                                self.config['lr_adapt_threshold']):
                tuned_base_lr = self.base_lr / 10.0
                    
        if self.config['train_mode'] == 'cdd':
            self.shared_lr.set_value(np.float32(tuned_base_lr))
        elif self.config['train_mode'] == 'avg':
            self.shared_lr.set_value(np.float32(tuned_base_lr*np.sqrt(size)))
        
        if self.verbose: 
            print 'Learning rate now: %.10f' % np.float32(self.shared_lr.get_value())  
            
            
    def load_params(self):
        
        # wget !wget https://s3.amazonaws.com/lasagne/recipes/pretrained/imagenet/vgg_cnn_s.pkl
        
        import pickle

        with open('vgg_cnn_s.pkl') as f:
            model = pickle.load(f)
        
        # CLASSES = model['synset words']
        # MEAN_IMAGE = model['mean image']

        lasagne.layers.set_all_param_values(self.output_layer, model['values'])
    