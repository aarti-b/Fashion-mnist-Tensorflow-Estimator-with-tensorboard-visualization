import gzip
import os
import shutil

import numpy as np
from six.moves import urllib
import tensorflow as tf


def read32(bytestream):
    """Read 4 bytes from bytestream as an unsigned 32-bit integer."""
    dt = np.dtype(np.uint32).newbyteorder('>')
    return np.frombuffer(bytestream.read(4), dtype=dt)[0]


def check_image_file_header(filename):
    """Validate that filename corresponds to images for the FMNIST dataset."""
    with tf.gfile.Open(filename, 'rb') as f:
        magic = read32(f)
        read32(f)  # num_images, unused
        rows = read32(f)
        cols = read32(f)
        if magic != 2051:
            raise ValueError('Invalid magic number %d in FMNIST file %s' % (magic, f.name))
        if rows != 28 or cols != 28:
            raise ValueError(
                    'Invalid FMNIST file %s: Expected 28x28 images, found %dx%d' %
                    (f.name, rows, cols))


def check_labels_file_header(filename):
    """Validate that filename corresponds to labels for the FMNIST dataset."""
    with tf.gfile.Open(filename, 'rb') as f:
        magic = read32(f)
        read32(f)  # num_items, unused
        if magic != 2049:
            raise ValueError('Invalid magic number %d in FMNIST file %s' % (magic, f.name))


def download(directory, filename):
    """Download (and unzip) a file from the FMNIST dataset if not already done."""
    filepath = os.path.join(directory, filename)
    if tf.gfile.Exists(filepath):
        return filepath
    if not tf.gfile.Exists(directory):
        tf.gfile.MakeDirs(directory)

    url = "http://fashion-mnist.s3-website.eu-central-1.amazonaws.com/" + filename + ".gz"

    zipped_filepath = filepath + '.gz'
    print('Downloading %s to %s' % (url, zipped_filepath))
    urllib.request.urlretrieve(url, zipped_filepath)
    with gzip.open(zipped_filepath, 'rb') as f_in, open(filepath, 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)
    os.remove(zipped_filepath)
    return filepath


def dataset(directory, images_file, labels_file):
    """Download and parse FMNIST dataset."""

    images_file = download(directory, images_file)
    labels_file = download(directory, labels_file)

    check_image_file_header(images_file)
    check_labels_file_header(labels_file)

    def decode_image(image):
        # Normalize from [0, 255] to [0.0, 1.0]
        image = tf.decode_raw(image, tf.uint8)
        image = tf.cast(image, tf.float32)
        image = tf.reshape(image, [784])
        return image / 255.0

    def decode_label(label):
        label = tf.decode_raw(label, tf.uint8)  
        label = tf.reshape(label, [])  
        return tf.to_int32(label)

    images = tf.data.FixedLengthRecordDataset(images_file, 28 * 28, header_bytes=16)
    images = images.map(decode_image)
    labels = tf.data.FixedLengthRecordDataset(labels_file, 1, header_bytes=8).map(decode_label)
    return tf.data.Dataset.zip((images, labels))


def train(directory):
    """tf.data.Dataset object for FMNIST training data."""
    return dataset(directory, 'train-images-idx3-ubyte',
                   'train-labels-idx1-ubyte')


def test(directory):
    """tf.data.Dataset object for FMNIST test data."""
    return dataset(directory, 't10k-images-idx3-ubyte', 't10k-labels-idx1-ubyte')
