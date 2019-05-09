import tensorflow as tf
from tfutils import w, b, conv_out_size
import constants as c


# noinspection PyShadowingNames
class DScaleModel:
    """
    A DScaleModel is a network that takes as input one video frame and attempts to discriminate
    whether or not the output frame is a real-world image or one generated by a generator network.
    Multiple of these are used together in a DiscriminatorModel to make predictions on frames at
    increasing scales.
    """

    def __init__(self, scale_index, height, width, conv_layer_fms, kernel_sizes, fc_layer_sizes):
        """
        Initializes the DScaleModel.

        @param scale_index: The index number of this height in the GeneratorModel.
        @param height: The height of the input images.
        @param width: The width of the input images.
        @param conv_layer_fms: The number of output feature maps for each convolution.
        @param kernel_sizes: The size of the kernel for each convolutional layer.
        @param fc_layer_sizes: The number of nodes in each fully-connected layer.

        @type scale_index: int
        @type height: int
        @type width: int
        @type conv_layer_fms: list<int>
        @type kernel_sizes: list<int> (len = len(scale_layer_fms) - 1)
        @type fc_layer_sizes: list<int>
        """
        assert len(kernel_sizes) == len(conv_layer_fms) - 1, \
            'len(kernel_sizes) must = len(conv_layer_fms) - 1'

        self.scale_index = scale_index
        self.height = height
        self.width = width
        self.conv_layer_fms = conv_layer_fms
        self.kernel_sizes = kernel_sizes
        self.fc_layer_sizes = fc_layer_sizes

        self.define_graph()

    # noinspection PyAttributeOutsideInit
    def define_graph(self):
        """
        Sets up the model graph in TensorFlow.
        """

        ##
        # Input data
        ##
        with tf.name_scope('input'):
            self.input_frames = tf.placeholder(
                tf.float32, shape=[None, self.height, self.width, self.conv_layer_fms[0]])

            # use variable batch_size for more flexibility
            self.batch_size = tf.shape(self.input_frames)[0]

        ##
        # Layer setup
        ##

        with tf.name_scope('setup'):
            # convolution
            with tf.name_scope('convolutions'):
                conv_ws = []
                conv_bs = []
                last_out_height = self.height
                last_out_width = self.width
                for i in range(len(self.kernel_sizes)):
                    conv_ws.append(w([self.kernel_sizes[i],
                                      self.kernel_sizes[i],
                                      self.conv_layer_fms[i],
                                      self.conv_layer_fms[i + 1]]))
                    conv_bs.append(b([self.conv_layer_fms[i + 1]]))

                    last_out_height = conv_out_size(
                        last_out_height, c.PADDING_D, self.kernel_sizes[i], 1)
                    last_out_width = conv_out_size(
                        last_out_width, c.PADDING_D, self.kernel_sizes[i], 1)

            # fully-connected
            with tf.name_scope('full-connected'):
                # Add in an initial layer to go from the last conv to the first fully-connected.
                # Use /2 for the height and width because there is a 2x2 pooling layer
                self.fc_layer_sizes.insert(
                    0, (last_out_height / 2) * (last_out_width / 2) * self.conv_layer_fms[-1])

                fc_ws = []
                fc_bs = []
                for i in range(len(self.fc_layer_sizes) - 1):
                    fc_ws.append(w([self.fc_layer_sizes[i],
                                    self.fc_layer_sizes[i + 1]]))
                    fc_bs.append(b([self.fc_layer_sizes[i + 1]]))

        ##
        # Forward pass calculation
        ##

        def generate_predictions():
            """
            Runs self.input_frames through the network to generate a prediction from 0
            (generated img) to 1 (real img).

            @return: A tensor of predictions of shape [self.batch_size x 1].
            """
            with tf.name_scope('calculation'):
                preds = tf.zeros([self.batch_size, 1])
                last_input = self.input_frames

                # convolutions
                with tf.name_scope('convolutions'):
                    for i in range(len(conv_ws)):
                        # Convolve layer and activate with ReLU
                        preds = tf.nn.conv2d(
                            last_input, conv_ws[i], [1, 1, 1, 1], padding=c.PADDING_D)
                        preds = tf.nn.relu(preds + conv_bs[i])

                        last_input = preds

                # pooling layer
                with tf.name_scope('pooling'):
                    preds = tf.nn.max_pool(preds, [1, 2, 2, 1], [1, 2, 2, 1], padding=c.PADDING_D)

                # flatten preds for dense layers
                shape = preds.get_shape().as_list()
                # -1 can be used as one dimension to size dynamically
                preds = tf.reshape(preds, [-1, shape[1] * shape[2] * shape[3]])

                # fully-connected layers
                with tf.name_scope('fully-connected'):
                    for i in range(len(fc_ws)):
                        preds = tf.matmul(preds, fc_ws[i]) + fc_bs[i]

                        # Activate with ReLU (or Sigmoid for last layer)
                        if i == len(fc_ws) - 1:
                            preds = tf.sigmoid(preds)
                        else:
                            preds = tf.nn.relu(preds)

                # clip preds between [.1, 0.9] for stability
                with tf.name_scope('clip'):
                    preds = tf.clip_by_value(preds, 0.1, 0.9)

                return preds

        self.preds = generate_predictions()

        ##
        # Training handled by DiscriminatorModel
        ##
