# -*- coding: utf-8 -*-
"""Style Transfer Tutorial.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1yibKw8wjYw-myCw27MuM9_5aBRQicg4D

# Style Transfer

Every painter has it's own style of painting. Style could be represented by dominating colors, strokes of the brush, reoccuring patterns or objects.

Style transfer - technique of transferring frequently reoccuring features of one image to other image without affecting contents a lot.

Original paper: [https://arxiv.org/abs/1508.06576](https://arxiv.org/abs/1508.06576)

Good explanation: [https://sefiks.com/2018/07/20/artistic-style-transfer-with-deep-learning/](https://sefiks.com/2018/07/20/artistic-style-transfer-with-deep-learning/)

We already know, that convolutional neural networks layers represent various levels of features. The deeper the layer - the higher the level of features being represented. First layers may represent lines, corners, points. Intermediate layers may represent geometrical figures made from lines, corners and points. Deeper layers may represent objects made from geometrical figures.

Let's start from the main imports and setting the variables.

Note: This example works very slow on CPU so GPU is recommended.
"""

from google.colab import drive
drive.mount('/content/drive')

import os
#os.environ['CUDA_VISIBLE_DEVICES'] = '-1' # '-1' is CPU

"""We will use VGG19, but you are free to try some other pre-trained model."""

import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras.applications import vgg19

base_image_path = "Your base image path.jpg"
#1
style_reference_image_path = "Your reference / style image path.png"

# To save the result
result_prefix = os.path.splitext(base_image_path)[0] + "_" + os.path.splitext(style_reference_image_path)[0] + "_generated"

# Weights of the different loss components
style_weight = 0.2 # How much style to transfer
content_weight = 0.025 # How much content to transfer from base image

"""Let's display the base and style images."""

from IPython.display import Image, display

display(Image(base_image_path))
display(Image(style_reference_image_path))

"""Image should be pre-processed before being supplied to the model. And modified image should be "de-processed" back so it could be displayed.

In pre-processing we add one more dimension for mini-batch, then use built-in vgg19 function to shift every channel to 0 mean value.
"""

def preprocess_image(image_path, img_nrows, img_ncols):
    # Util function to open, resize and format pictures into appropriate tensors
    img = keras.preprocessing.image.load_img(
        image_path, target_size=(img_nrows, img_ncols)
    )
    img = keras.preprocessing.image.img_to_array(img)
    img = np.expand_dims(img, axis=0)
    #img = vgg16.preprocess_input(img)
    img = vgg19.preprocess_input(img)
    return tf.convert_to_tensor(img)

"""In "de-processing" we shift the resulting image channels values back. Change channels order back to RGB and clip values which are outside of 255 range. Finally we convert image to `uint8` to display."""

def deprocess_image(x, img_nrows, img_ncols):
    # Util function to convert a tensor into a valid image
    x = x.reshape((img_nrows, img_ncols, 3))
    # Remove zero-center by mean pixel
    x[:, :, 0] += 103.939
    x[:, :, 1] += 116.779
    x[:, :, 2] += 123.68
    # 'BGR'->'RGB'
    x = x[:, :, ::-1]
    x = np.clip(x, 0, 255).astype("uint8")
    return x

"""The gram matrix is the main reason style transfering works as it is. Gram matrix is matrix multiplied by transposed itself.

"""

# The gram matrix of an image tensor (feature-wise outer product)

def gram_matrix(x):
    x = tf.transpose(x, (2, 0, 1))
    features = tf.reshape(x, (tf.shape(x)[0], -1))
    gram = tf.matmul(features, tf.transpose(features))
    return gram

# The "style loss" is designed to maintain
# the style of the reference image in the generated image.
# It is based on the gram matrices (which capture style) of
# feature maps from the style reference image
# and from the generated image


def style_loss(style, combination, img_nrows, img_ncols):
    S = gram_matrix(style)
    C = gram_matrix(combination)
    channels = 3
    size = img_nrows * img_ncols
    return tf.reduce_sum(tf.square(S - C)) / (4.0 * (channels ** 2) * (size ** 2))

# An auxiliary loss function
# designed to maintain the "content" of the
# base image in the generated image


def content_loss(base, combination):
    return tf.reduce_sum(tf.square(combination - base))

"""Now we can build the model. Outputs will be all layers of the model."""

# Build model loaded with pre-trained ImageNet weights
model = vgg19.VGG19(weights="imagenet", include_top=False)

# Get the symbolic outputs of each "key" layer (we gave them unique names).
outputs_dict = dict([(layer.name, layer.output) for layer in model.layers])

# Set up a model that returns the activation values for every layer in outputs_dict
feature_extractor = keras.Model(inputs=model.inputs, outputs=outputs_dict)

model.summary()

"""Now we can select the needed layers for style and content. For vgg style model for better effect it is recommended to use layers right after shrinking (max pooling). Layer for contents was chosen the same as mentioned in paper."""

# List of layers to use for the style loss.
style_layer_names = [
    "block1_conv1",
    "block2_conv1",
    "block3_conv1",
    "block4_conv1",
    "block5_conv1",
]
# The layer to use for the content loss.
content_layer_name = "block5_conv2"

"""Now we may define the computation of the total loss which could be simplified to this: `loss = content_weight * content_loss + style_weight * style_loss`"""

def compute_loss(combination_image, base_image, style_reference_image, img_nrows, img_ncols):
    input_tensor = tf.concat(
        [base_image, style_reference_image, combination_image], axis=0
    )
    features = feature_extractor(input_tensor)

    # Initialize the loss
    loss = tf.zeros(shape=())

    # Add content loss
    layer_features = features[content_layer_name]
    base_image_features = layer_features[0, :, :, :]
    combination_features = layer_features[2, :, :, :]
    loss = loss + content_weight * content_loss(
        base_image_features, combination_features
    )
    # Add style loss
    for layer_name in style_layer_names:
        layer_features = features[layer_name]
        style_reference_features = layer_features[1, :, :, :]
        combination_features = layer_features[2, :, :, :]
        sl = style_loss(style_reference_features, combination_features, img_nrows, img_ncols)
        loss += (style_weight / len(style_layer_names)) * sl

    return loss

"""Now when we have prepared all basic functions, the training could be started."""

@tf.function
def compute_loss_and_grads(combination_image, base_image, style_reference_image, img_nrows, img_ncols):
    with tf.GradientTape() as tape:
        loss = compute_loss(combination_image, base_image, style_reference_image, img_nrows, img_ncols)
    grads = tape.gradient(loss, combination_image)
    return loss, grads

# Adam optimizer is a different from one that was proposed in paper (as one in paper is not implemented in keras/tf)
optimizer = keras.optimizers.Adam(
    keras.optimizers.schedules.ExponentialDecay(
        initial_learning_rate=1.0, decay_steps=100, decay_rate=0.96
    )
)


# Dimensions of the generated picture.
width, height = keras.preprocessing.image.load_img(base_image_path).size
img_nrows = 400
img_ncols = int(width * img_nrows / height)

# We need noise image according to original paper
noise_image = np.random.randint(256, size=(1, img_nrows, img_ncols, 3)).astype(np.float32)

# Loading of base image
base_image = keras.preprocessing.image.load_img(base_image_path, target_size=(img_nrows, img_ncols))
base_image = keras.preprocessing.image.img_to_array(base_image)
base_image = np.expand_dims(base_image, axis=0)
# When generating initial combination_image instead of a random noise
# we combine noise with a base image to speed up training a bit
combination_image = (0.2 * noise_image + 0.7 * base_image)

base_image = tf.convert_to_tensor(vgg19.preprocess_input(base_image))
combination_image = tf.Variable(tf.convert_to_tensor(vgg19.preprocess_input(combination_image)))
style_reference_image = preprocess_image(style_reference_image_path, img_nrows, img_ncols)


# Define the save path
save_path = "save path"

# Initialize the counter for saved images
save_counter = 1

iterations = 2000 # initial results could be seen after 100 iterations, but for better results ~2000 iteration needed
for i in range(1, iterations + 1):
    # Calculate loss and gradients
    loss, grads = compute_loss_and_grads(
        combination_image, base_image, style_reference_image, img_nrows, img_ncols
    )
    # Apply gradients to combination_image
    optimizer.apply_gradients([(grads, combination_image)])

    # Save every fifth image and name them from 1 to 8
    if i % 2000 == 0 and save_counter <= 8:
        img = deprocess_image(combination_image.numpy(), img_nrows, img_ncols)
        fname = f"{save_path}{save_counter} style.png"
        keras.preprocessing.image.save_img(fname, img)
        save_counter += 1

    if i % 500 == 0:
        print("Iteration %d: loss=%.2f" % (i, loss))

"""Now we can check the result:"""

display(Image(result_prefix + "_at_iteration_2000.png"))