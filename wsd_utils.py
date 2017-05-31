# Copyright 2015 Google Inc.
# Copyright 2017 Johns Hopkins University (Nicholas Andrews).
#
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

import gzip
import os
import re
import tarfile

from six.moves import urllib
import tensorflow as tf

# Special vocabulary symbols - we always put them at the start.
_PAD = "_PAD"
_HELDOUT = "_HELDOUT"
_EOS = "_EOS"
_UNK = "_CHAR_UNK"
_SPACE = "_SPACE"
_START_VOCAB = [_PAD, _HELDOUT, _EOS, _UNK]

PAD_ID = 0
HELDOUT_ID = 1
EOS_ID = 2
UNK_ID = 3

# Regular expressions used to tokenize.
_CHAR_MARKER = "_CHAR_"
_CHAR_MARKER_LEN = len(_CHAR_MARKER)
_SPEC_CHARS = "" + chr(226) + chr(153) + chr(128)
_PUNCTUATION = "][.,!?\"':;%$#@&*+}{|><=/^~)(_`,0123456789" + _SPEC_CHARS + "-"
_WORD_SPLIT = re.compile("([" + _PUNCTUATION + "])")
_OLD_WORD_SPLIT = re.compile("([.,!?\"':;)(])")
_DIGIT_RE = re.compile("\d")

# Data locations
_PTB_URL = "http://www.fit.vutbr.cz/~imikolov/rnnlm/simple-examples.tgz"

def calculate_buckets_scale(data_set, buckets):
  """Calculate buckets scales for the given data set."""
  train_bucket_sizes = [len(data_set[b]) for b in xrange(len(buckets))]
  train_total_size = max(1, float(sum(train_bucket_sizes)))

  train_buckets_scale.append(
    [sum(train_bucket_sizes[:i + 1]) / train_total_size
     for i in xrange(len(train_bucket_sizes))])

  return train_total_size

def read_data(source_path, buckets, max_size=None, print_out=True):
  """Read data from source and put into buckets.

  Args:
    source_path: path to the file with token-ids
    buckets: the buckets to use.
    max_size: maximum number of lines to read, all other will be ignored;
      if 0 or None, data files will be read completely (no limit).
      If set to 1, no data will be returned (empty lists of the right form).
    print_out: whether to print out status or not.

  Returns:
    data_set: a list of length len(_buckets); data_set[n] contains a list of
      (source, target) pairs read from the provided data files that fit
      into the n-th bucket, i.e., such that len(source) < _buckets[n][0] and
      len(target) < _buckets[n][1]; source and target are lists of token-ids.
  """
  data_set = [[] for _ in buckets]
  counter = 0
  if max_size != 1:
    with tf.gfile.GFile(source_path, mode="r") as source_file:
      source = source_file.readline()
      while source and (not max_size or counter < max_size):
        counter += 1
        if counter % 100000 == 0 and print_out:
          tf.logging.info("\treading data line {}".format(counter))
        source_ids = [int(x) for x in source.split()]
        source_ids, source_len = zero_split(source_ids)

        ## Create instances
        for i in range(len(source_ids)):
          target = copy_source_ids[i]
          if target in set([PAD_ID, HELDOUT_ID, EOS_ID, UNK_ID]):
            continue
          copy_source_ids = list(copy_source_ids)
          copy_source_ids[i] = HELDOUT_ID
          for bucket_id, size in enumerate(buckets):
            if source_len <= size and target_len <= size:
              data_set[bucket_id].append([source_ids, target_ids])
              break

        # Read the next line
        source = source_file.readline()
  return data_set

def maybe_download(directory, filename, url):
  """Download filename from url unless it's already in directory."""
  if not tf.gfile.Exists(directory):
    tf.logging.info("Creating directory %s" % directory)
    os.mkdir(directory)
  filepath = os.path.join(directory, filename)
  if not tf.gfile.Exists(filepath):
    tf.logging.info("Downloading %s to %s" % (url, filepath))
    filepath, _ = urllib.request.urlretrieve(url, filepath)
    statinfo = os.stat(filepath)
    tf.logging.info("Successfully downloaded", filename, statinfo.st_size,
                    "bytes")
  return filepath

def get_ptb_train_set(directory):
  train_path = os.path.join(directory, "simple-examples/data/ptb.train.txt")
  if not (tf.gfile.Exists(train_path)):
    corpus_file = maybe_download(directory, "ptb.tgz", _PTB_URL)
    tf.logging.info("Extracting tar file %s" % corpus_file)
    with tarfile.open(corpus_file, "r") as corpus_tar:
      corpus_tar.extractall(directory)
  return train_path

def get_ptb_dev_set(directory):
  valid_path = os.path.join(directory, "simple-examples/data/ptb.valid.txt")
  if not (tf.gfile.Exists(valid_path)):
    corpus_file = maybe_download(directory, "ptb.tgz", _PTB_URL)
    tf.logging.info("Extracting tar file %s" % corpus_file)
    with tarfile.open(corpus_file, "r") as corpus_tar:
      corpus_tar.extractall(directory)
  return valid_path

def is_char(token):
  if len(token) > _CHAR_MARKER_LEN:
    if token[:_CHAR_MARKER_LEN] == _CHAR_MARKER:
      return True
  return False

def basic_detokenizer(tokens):
  """Reverse the process of the basic tokenizer below."""
  result = []
  previous_nospace = True
  for t in tokens:
    if is_char(t):
      result.append(t[_CHAR_MARKER_LEN:])
      previous_nospace = True
    elif t == _SPACE:
      result.append(" ")
      previous_nospace = True
    elif previous_nospace:
      result.append(t)
      previous_nospace = False
    else:
      result.extend([" ", t])
      previous_nospace = False
  return "".join(result)

old_style = False

def basic_tokenizer(sentence):
  """Very basic tokenizer: split the sentence into a list of tokens."""
  words = []
  if old_style:
    for space_separated_fragment in sentence.strip().split():
      words.extend(re.split(_OLD_WORD_SPLIT, space_separated_fragment))
    return [w for w in words if w]
  for space_separated_fragment in sentence.strip().split():
    tokens = [t for t in re.split(_WORD_SPLIT, space_separated_fragment) if t]
    first_is_char = False
    for i, t in enumerate(tokens):
      if len(t) == 1 and t in _PUNCTUATION:
        tokens[i] = _CHAR_MARKER + t
        if i == 0:
          first_is_char = True
    if words and words[-1] != _SPACE and (first_is_char or is_char(words[-1])):
      tokens = [_SPACE] + tokens
    spaced_tokens = []
    for i, tok in enumerate(tokens):
      spaced_tokens.append(tokens[i])
      if i < len(tokens) - 1:
        if tok != _SPACE and not (is_char(tok) or is_char(tokens[i+1])):
          spaced_tokens.append(_SPACE)
    words.extend(spaced_tokens)
  return words

def space_tokenizer(sentence):
  return sentence.strip().split()

def create_vocabulary(vocab_path, data_path, tokenizer,
                      max_vocabulary_size=None, normalize_digits=False):
  """Create vocabulary file from data file.

  Data file is assumed to contain one sentence per line. Each sentence is
  tokenized and digits are normalized (if normalize_digits is set).
  Vocabulary contains the most-frequent tokens up to max_vocabulary_size.
  We write it to vocabulary_path in a one-token-per-line format, so that later
  token in the first line gets id=0, second line gets id=1, and so on.

  Args:
    vocabulary_path: path where the vocabulary will be created.
    data_path: data file that will be used to create vocabulary.
    max_vocabulary_size: limit on the size of the created vocabulary.
    tokenizer: a function to use to tokenize each data sentence;
      if None, basic_tokenizer will be used.
    normalize_digits: Boolean; if true, all digits are replaced by 0s.
  """
  #if not tf.gfile.Exists(vocab_path):
  if True:
    tf.logging.info("Creating vocabulary {} from data {}".format(vocab_path,
                                                                 data_path))
    vocab = {}
    with tf.gfile.GFile(data_path, mode="r") as f:
      counter = 0
      for line_in in f:
        line = " ".join(line_in.split())
        counter += 1
        if counter % 100000 == 0:
          tf.logging.info("processing en line %d" % counter)

        tokens = tokenizer(line)
        for w in tokens:
          word = re.sub(_DIGIT_RE, "0", w) if normalize_digits else w
          if word in vocab:
            vocab[word] += 1
          else:
            vocab[word] = 1

      sorted_vocab = sorted(vocab, key=vocab.get, reverse=True)

      vocab_list = _START_VOCAB + sorted_vocab
      if max_vocabulary_size and len(vocab_list) > max_vocabulary_size:
        tf.logging.info("{} > {}; truncating vocab".format(
          len(vocab_list),
          max_vocabulary_size
        ))
        vocab_list = vocab_list[:max_vocabulary_size]
      assert len(vocab_list) > 0
      with tf.gfile.GFile(vocab_path, mode="w") as vocab_file:
        for w in vocab_list:
          vocab_file.write(str(w) + "\n")

def initialize_vocabulary(vocabulary_path):
  """Initialize vocabulary from file.

  We assume the vocabulary is stored one-item-per-line, so a file:
    dog
    cat
  will result in a vocabulary {"dog": 0, "cat": 1}, and this function will
  also return the reversed-vocabulary ["dog", "cat"].

  Args:
    vocabulary_path: path to the file containing the vocabulary.

  Returns:
    a pair: the vocabulary (a dictionary mapping string to integers), and
    the reversed vocabulary (a list, which reverses the vocabulary mapping).

  Raises:
    ValueError: if the provided vocabulary_path does not exist.
  """
  if tf.gfile.Exists(vocabulary_path):
    rev_vocab = []
    with tf.gfile.GFile(vocabulary_path, mode="rb") as f:
      rev_vocab.extend(f.readlines())
    rev_vocab = [line.strip() for line in rev_vocab]
    vocab = dict([(x, y) for (y, x) in enumerate(rev_vocab)])
    return vocab, rev_vocab
  else:
    raise ValueError("Vocabulary file %s not found.", vocabulary_path)

def sentence_to_token_ids(sentence, vocabulary, tokenizer,
                          normalize_digits=old_style):
  """Convert a string to list of integers representing token-ids.

  For example, a sentence "I have a dog" may become tokenized into
  ["I", "have", "a", "dog"] and with vocabulary {"I": 1, "have": 2,
  "a": 4, "dog": 7"} this function will return [1, 2, 4, 7].

  Args:
    sentence: the sentence in bytes format to convert to token-ids.
    vocabulary: a dictionary mapping tokens to integers.
    tokenizer: a function to use to tokenize each sentence;
      if None, basic_tokenizer will be used.
    normalize_digits: Boolean; if true, all digits are replaced by 0s.

  Returns:
    a list of integers, the token-ids for the sentence.
  """
  words = tokenizer(sentence)
  result = []
  for w in words:
    if normalize_digits:
      w = re.sub(_DIGIT_RE, "0", w)
    if w in vocabulary:
      result.append(vocabulary[w])
    else:
      result.append(UNK_ID)
  return result

def data_to_token_ids(data_path, target_path, vocabulary_path, tokenizer,
                      normalize_digits=False):
  """Tokenize data file and turn into token-ids using given vocabulary file.

  This function loads data line-by-line from data_path, calls the above
  sentence_to_token_ids, and saves the result to target_path. See comment
  for sentence_to_token_ids on the details of token-ids format.

  Args:
    data_path: path to the data file in one-sentence-per-line format.
    target_path: path where the file with token-ids will be created.
    vocabulary_path: path to the vocabulary file.
    tokenizer: a function to use to tokenize each sentence;
      if None, basic_tokenizer will be used.
    normalize_digits: Boolean; if true, all digits are replaced by 0s.
  """
  if not tf.gfile.Exists(target_path):
    tf.logging.info("Tokenizing data in %s" % data_path)
    vocab, _ = initialize_vocabulary(vocabulary_path)
    with tf.gfile.GFile(data_path, mode="r") as data_file:
      with tf.gfile.GFile(target_path, mode="w") as tokens_file:
        counter = 0
        for line in data_file:
          counter += 1
          if counter % 100000 == 0:
            tf.logging.info("tokenizing line %d" % counter)
          token_ids = sentence_to_token_ids(line, vocab, tokenizer,
                                            normalize_digits)
          tokens_file.write(" ".join([str(tok) for tok in token_ids]) + "\n")

def prepare_ptb_data(data_dir, tokenizer,
                     vocabulary_size=100000,
                     normalize_digits=False):
  """ Create vocabularies and tokenize data.

  Args:
    data_dir: directory in which the data sets will be stored.
    vocabulary_size: size of the joint vocabulary to create and use.
    tokenizer: a function to use to tokenize each data sentence;
      if None, basic_tokenizer will be used.
    normalize_digits: Boolean; if true, all digits are replaced by 0s.

  Returns:
    A tuple of 3 elements:
      (1) path to the token-ids for training data-set,
      (2) path to the token-ids for development data-set,
      (3) path to the vocabulary file,
  """

  # Get ptb data to the specified directory.
  train_path = get_ptb_train_set(data_dir)
  tf.logging.info('PTB train set: {}'.format(train_path))
  dev_path = get_ptb_dev_set(data_dir)
  tf.logging.info("PTB dev set: {}".format(dev_path))

  # Create vocabularies of the appropriate sizes.
  vocab_path = os.path.join(data_dir, "vocab%d.txt" % vocabulary_size)
  create_vocabulary(vocab_path, train_path, tokenizer,
                    max_vocabulary_size=vocabulary_size,
                    normalize_digits=normalize_digits)
  tf.logging.info('Vocabulary path: {}'.format(vocab_path))

  # Create token ids for the training data.
  train_ids_path = train_path + (".%d.ids" % vocabulary_size)
  data_to_token_ids(train_path, train_ids_path, vocab_path,
                    tokenizer, normalize_digits=normalize_digits)
  tf.logging.info('PTB train ids path: {}'.format(train_ids_path))

  # Create token ids for the development data.
  dev_ids_path = dev_path + (".%d.ids" % vocabulary_size)
  data_to_token_ids(dev_path, dev_ids_path, vocab_path,
                    tokenizer, normalize_digits=normalize_digits)
  tf.logging.info('PTB dev ids path: {}'.format(dev_ids_path))

  return (train_ids_path, dev_ids_path, vocab_path)

def num_lines(path):
  with open(path) as f:
    ret = 0
    for line in f:
      ret += 1
    return ret

class DataTest(tf.test.TestCase):
  def test(self):
    tmpdatadir = tf.test.get_temp_dir()
    train_ids_path, dev_ids_path, vocab_path = prepare_ptb_data(
      tmpdatadir,
      space_tokenizer,
      vocabulary_size=9000)

    tf.logging.info('train: {}'.format(train_ids_path))
    tf.logging.info('valid: {}'.format(dev_ids_path))
    tf.logging.info('vocab: {}'.format(vocab_path))

    assert num_lines(train_ids_path) > 0
    assert num_lines(dev_ids_path) > 0
    assert num_lines(vocab_path) > 0

    read_data(train_ids_path)

if __name__ == "__main__":
  tf.logging.set_verbosity(tf.logging.INFO)
  tf.test.main()