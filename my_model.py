import tensorflow as tf
import numpy as np
import time
from datetime import timedelta
import os

# 按概率从概率最大的n个字中选一个
def pick_top_n(preds, vocab_size, top_n=5):
    p = np.squeeze(preds)
    p[np.argsort(p)[:-top_n]] = 0
    p = p/np.sum(p) #归一化啊，不归一化怎么能叫概率呢，长点心吧
    return np.random.choice(vocab_size, 1, p=p)[0]


class CharRNN:
    def __init__(self,num_classes, num_seqs=64, num_steps=50, lstm_size=128, num_layers=2, learning_rate=0.001,
                 grad_clip=5, sampling=False, train_keep_prob=0.5, use_embedding=False, embedding_size=128):

        if sampling is True:
            num_seqs = 1
            num_steps = 1

        self.num_classes = num_classes
        self.num_seqs = num_seqs
        self.num_steps = num_steps
        self.lstm_size = lstm_size
        self.num_layers = num_layers
        self.learning_rate = learning_rate
        self.grad_clip = grad_clip
        self.train_keep_prob = train_keep_prob
        self.use_embedding = use_embedding
        self.embedding_size = embedding_size

        tf.reset_default_graph()
        self.build_inputs()
        self.build_lstm()
        self.build_loss()
        self.build_optimizer()

        self.saver = tf.train.Saver()

    # 输入
    def build_inputs(self):
        self.inputs = tf.placeholder(tf.int32, [None, self.num_steps])
        self.targets = tf.placeholder(tf.int32, [None, self.num_steps])
        self.keep_prob = tf.placeholder(tf.float32)

        if self.use_embedding is True:
            embedding = tf.get_variable('embedding', [self.num_classes, self.embedding_size])
            self.lstm_inputs = tf.nn.embedding_lookup(embedding, self.inputs)
        else:
            self.lstm_inputs = tf.one_hot(self.inputs, self.num_classes)

    # 采用embedding + 双层lstm结构 + 一层dense layer
    def build_lstm(self):
        def get_a_cell(lstm_size, keep_prob):
            lstm = tf.contrib.rnn.BasicLSTMCell(lstm_size,state_is_tuple=True)
            drop = tf.contrib.rnn.DropoutWrapper(lstm, output_keep_prob=keep_prob)
            return drop

        cell = tf.contrib.rnn.MultiRNNCell(
            [get_a_cell(self.lstm_size, self.keep_prob) for _ in range(self.num_layers)], state_is_tuple=True
        )

        self.initial_state = cell.zero_state(self.num_seqs, tf.float32)

        self.lstm_outputs, self.final_states = tf.nn.dynamic_rnn(cell, self.lstm_inputs, initial_state=self.initial_state)
        x = tf.reshape(self.lstm_outputs, [-1, self.embedding_size])

        self.logits = tf.layers.dense(x, self.num_classes)
        self.proba_prediction = tf.nn.softmax(self.logits)

    def build_loss(self):
        self.y_one_hot = tf.one_hot(self.targets, self.num_classes)
        self.y_reshaped = tf.reshape(self.y_one_hot, [-1, self.num_classes])
        loss = tf.nn.softmax_cross_entropy_with_logits(logits=self.logits, labels=self.y_reshaped)
        self.loss = tf.reduce_mean(loss)

    # 为了防止过拟合，采用了截断最大梯度的方法
    def build_optimizer(self):
        tvars = tf.trainable_variables()
        grads, _ = tf.clip_by_global_norm(tf.gradients(self.loss, tvars), clip_norm=self.grad_clip)
        train_op = tf.train.AdamOptimizer(learning_rate=self.learning_rate)
        self.optim = train_op.apply_gradients(zip(grads, tvars))

    # 训练
    def train(self, batch_generator, max_step, save_path, save_per_n, log_per_n):
        self.session = tf.Session()
        with self.session as sess:
            sess.run(tf.global_variables_initializer())
            # start training
            step = 0
            new_state = sess.run(self.initial_state)
            for train_x, train_y in batch_generator:
                step += 1
                start_time = time.time()
                feed = {self.inputs: train_x,
                        self.targets: train_y,
                        self.keep_prob: self.train_keep_prob,
                        self.initial_state: new_state}

                batch_loss, new_state, _ = sess.run([self.loss, self.final_states, self.optim], feed_dict=feed)

                if step%log_per_n == 0:
                    end_time = time.time()
                    use_time = timedelta(seconds=int(round(end_time - start_time)))
                    print('step {}/{}'.format(step, max_step),
                          'batch_loss = {}'.format(batch_loss),
                          'use_time = {}'.format(use_time))

                if step%save_per_n == 0:
                    self.saver.save(sess, os.path.join(save_path, 'model'), global_step=step)

                if step>=max_step:
                    break
            self.saver.save(sess, os.path.join(save_path, 'model'), global_step=step)

    # 采样，prime是给定的开头，n_samples是要生成的字的数量
    def sample(self, n_samples, prime, vocab_size):
        samples = list(prime)
        sess = self.session
        new_state = sess.run(self.initial_state)
        preds = np.zeros((vocab_size,))
        for c in prime:
            x = np.ones((1, 1))
            x[0, 0] = c
            feed = {self.inputs: x,
                    self.keep_prob: 1,
                    self.initial_state: new_state}
            preds, new_state = sess.run([self.proba_prediction, self.final_states], feed_dict=feed)

        c = pick_top_n(preds, vocab_size)
        samples.append(c)
        for i in range(n_samples):
            x = np.ones((1,1))
            x[0, 0] = c
            feed = {self.inputs: x,
                    self.keep_prob: 1,
                    self.initial_state: new_state}
            preds, new_state = sess.run([self.proba_prediction, self.final_states], feed_dict=feed)
            c = pick_top_n(preds, vocab_size)
            samples.append(c)
        return np.array(samples)

    def load(self, checkpoint):
        self.session = tf.Session()
        self.saver.restore(self.session, checkpoint)
        print("restored from {}".format(checkpoint))












