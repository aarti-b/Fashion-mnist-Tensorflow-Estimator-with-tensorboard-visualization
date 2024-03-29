"""Define the model."""

import tensorflow as tf

from model.triplet_loss import batch_all_triplet_loss
from model.triplet_loss import batch_hard_triplet_loss
from model.triplet_loss import semi_hard_triplet_loss


def build_lenet_(is_training, images, params):
    """
    LeNet Model
    """

    num_channels = params.num_channels
    bn_momentum = params.bn_momentum
    channels = [num_channels, num_channels * 2]

    # Convolution Layer 1
    conv1 = tf.layers.conv2d(inputs=images,
                             filters=params.num_channels,
                             kernel_size=[5, 5],
                             padding="same",
                             activation=tf.nn.relu)

    # Pooling Layer 1
    pool1 = tf.layers.max_pooling2d(inputs=conv1, 
                                    pool_size=[2, 2],
                                    strides=2)

    # Convolution Layer 2
    conv2 = tf.layers.conv2d(inputs=pool1,
                             filters=64,
                             kernel_size=[5, 5],
                             padding="same",
                             activation=tf.nn.relu)

    if params.use_batch_norm:
        bn = tf.layers.batch_normalization(conv2, momentum=bn_momentum, training=is_training)

        # Pooling Layer 2
        pool2 = tf.layers.max_pooling2d(inputs=bn,
                                        pool_size=[2, 2],
                                        strides=2)

        # Dense Layer
        pool2_flat = tf.reshape(pool2, [-1, 7 * 7 * num_channels * 2])
        dense = tf.layers.dense(inputs=pool2_flat,
                                units=1024,
                                activation=tf.nn.relu)
        out = dense

    else: 

        # Pooling Layer 2
        pool2 = tf.layers.max_pooling2d(inputs=conv2,
                                        pool_size=[2, 2],
                                        strides=2)

        # Dense Layer
        pool2_flat = tf.reshape(pool2, [-1, 7 * 7 * 64])
        dense = tf.layers.dense(inputs=pool2_flat,
                                units=params.num_channels*2,
                                activation=tf.nn.relu)
        out = dense

    return out

def basic_model(is_training, images, params):

    """Compute outputs of the model (embeddings for triplet loss).

    Args:
        is_training: (bool) whether we are training or not
        images: (dict) contains the inputs of the graph (features)
                this can be `tf.placeholder` or outputs of `tf.data`
        params: (Params) hyperparameters

    Returns:
        output: (tf.Tensor) output of the model
    """
    
    out = images

    # Define the number of channels of each convolution
    num_channels = params.num_channels
    bn_momentum = params.bn_momentum
    channels = [num_channels, num_channels * 2]
    for i, c in enumerate(channels):
        with tf.variable_scope('block_{}'.format(i+1)):
            out = tf.layers.conv2d(out, c, 3, padding='same')
            if params.use_batch_norm:
                out = tf.layers.batch_normalization(out, momentum=bn_momentum, training=is_training)
            out = tf.nn.relu(out)
            out = tf.layers.max_pooling2d(out, 2, 2)

    assert out.shape[1:] == [7, 7, num_channels * 2]

    out = tf.reshape(out, [-1, 7 * 7 * num_channels * 2])
    with tf.variable_scope('fc_1'):
        out = tf.layers.dense(out, params.embedding_size)

    return out


def model_fn(features, labels, mode, params):
    """Model function for tf.estimator

    Args:
        features: input batch of images
        labels: labels of the images
        mode: can be one of tf.estimator.ModeKeys.{TRAIN, EVAL, PREDICT}
        params: contains hyperparameters of the model (ex: `params.learning_rate`)

    Returns:
        model_spec: tf.estimator.EstimatorSpec object
    """

    is_training = (mode == tf.estimator.ModeKeys.TRAIN)

    images = features
    images = tf.reshape(images, [-1, params.image_size, params.image_size, 1])
    assert images.shape[1:] == [params.image_size, params.image_size, 1], "{}".format(images.shape)

    # -----------------------------------------------------------

    with tf.variable_scope('model'):
        # Compute the embeddings with the model

        embeddings = build_lenet_(is_training, images, params)

    embedding_mean_norm = tf.reduce_mean(tf.norm(embeddings, axis=1))
    tf.summary.scalar("embedding_mean_norm", embedding_mean_norm)

    if mode == tf.estimator.ModeKeys.PREDICT:
        predictions = {'embeddings': embeddings}
        return tf.estimator.EstimatorSpec(mode=mode, predictions=predictions)

    labels = tf.cast(labels, tf.int64)

    # Define triplet loss
    if params.triplet_strategy == "batch_all":
        loss, fraction = batch_all_triplet_loss(labels, embeddings, margin=params.margin,
                                                squared=params.squared)

    elif params.triplet_strategy == "batch_hard":
        loss = batch_hard_triplet_loss(labels, embeddings, margin=params.margin,
                                       squared=params.squared)

    elif params.triplet_strategy== "batch_semi":
        loss = semi_hard_triplet_loss(labels, embeddings, margin=params.margin)

    else:
        raise ValueError("Triplet strategy not recognized: {}".format(params.triplet_strategy))


    '''------------------------------------------------------------------
     Metrics for evaluation using tf.metrics (average over whole dataset)
     --------------------------------------------------------------------
    '''


    with tf.variable_scope("metrics"):
        eval_metric_ops = {"embedding_mean_norm": tf.metrics.mean(embedding_mean_norm)}

        if params.triplet_strategy == "batch_all":
            eval_metric_ops['fraction_positive_triplets'] = tf.metrics.mean(fraction)

    if mode == tf.estimator.ModeKeys.EVAL:
        return tf.estimator.EstimatorSpec(mode, loss=loss, eval_metric_ops=eval_metric_ops)


    # Summaries for training
    tf.summary.scalar('loss', loss)
    if params.triplet_strategy == "batch_all":
        tf.summary.scalar('fraction_positive_triplets', fraction)
    tf.summary.image('train_image', images, max_outputs=1)

    # Define training step that minimizes the loss with the Adam optimizer
    optimizer = tf.train.AdamOptimizer(params.learning_rate)
    global_step = tf.train.get_global_step()

    if params.use_batch_norm:
        # Add a dependency to update the moving mean and variance for batch normalization
        with tf.control_dependencies(tf.get_collection(tf.GraphKeys.UPDATE_OPS)):
            train_op = optimizer.minimize(loss, global_step=global_step)
    else:
        train_op = optimizer.minimize(loss, global_step=global_step)

    return tf.estimator.EstimatorSpec(mode, loss=loss, train_op=train_op)
