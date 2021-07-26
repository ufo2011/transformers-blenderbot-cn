from BlenderbotSmall import TFBlenderbotSmallForConditionalGeneration, BlenderbotSmallConfig
import numpy as np
import tensorflow as tf
from tokenizer import SelfTokenizer


tokenizer = SelfTokenizer("vocab.json")


config = BlenderbotSmallConfig.from_json_file("model_file/config_small.json")


b_model = TFBlenderbotSmallForConditionalGeneration(config=config)


inp = tokenizer.encoder(["你好啊，我叫唐小书。"], return_tensor="tf")
lab = tokenizer.encoder(["唐小书，你好，我叫唐恩达，是来自中国，你也哪里人呢？"], return_tensor="tf")
model_inp = {
    "input_ids":inp["input_ids"],
    "attention_mask":inp["attention_mask"],
    "decoder_input_ids":lab["input_ids"]
}

b_model(model_inp)


b_model.summary()

def compute_loss(labels, logits):
    loss_fn = tf.keras.losses.SparseCategoricalCrossentropy(
        from_logits=True, reduction=tf.keras.losses.Reduction.NONE
    )
    active_loss = tf.not_equal(tf.reshape(labels, (-1,)), 0)
    reduced_logits = tf.boolean_mask(tf.reshape(logits, (-1, logits.shape[2])), active_loss)
    labels = tf.boolean_mask(tf.reshape(labels, (-1,)), active_loss)
    return loss_fn(labels, reduced_logits)

def accuracy(y_true, y_pred):

    active_loss = tf.not_equal(tf.reshape(y_true, (-1,)), 0)
    reduced_logits = tf.boolean_mask(tf.reshape(y_pred, (-1, y_pred.shape[2])), active_loss)
    labels = tf.boolean_mask(tf.reshape(y_true, (-1,)), active_loss)
    return tf.keras.metrics.sparse_categorical_accuracy(labels, reduced_logits)

def create_inputs_labels(path, size=None):
    with open(path, "r", encoding="utf-8") as f:
        data = f.readlines()

    q = []
    a = []
    data = [data[i][:-1] for i in range(len(data))]

    for n in data:
        if n == "":
            continue
        q_len = len(q)
        a_len = len(a)
        if q_len == a_len:
            q.append(n)
        else:
            a.append(n)

    inputs = tokenizer.encoder(q, add_special_tokens=True, padding=True, truncation=True, return_tensor="tf", max_len=150)
    labels = tokenizer.encoder(a, add_special_tokens=True, padding=True, truncation=True, return_tensor="tf", max_len=150)
    if size:
        return {
            "input_ids": inputs["input_ids"][:size],
            "attention_mask": inputs["attention_mask"][:size],
            "decoder_input_ids": labels["input_ids"][:size],
            "decoder_attention_mask": labels["attention_mask"][:size],
        }
    else:
        return {
            "input_ids":inputs["input_ids"],
            "attention_mask":inputs["attention_mask"],
            "decoder_input_ids":labels["input_ids"],
            "decoder_attention_mask":labels["attention_mask"],
        }


class NaturalExpDecay(tf.keras.optimizers.schedules.LearningRateSchedule):
    """学习率自然数衰减"""
    def __init__(self, initial_learning_rate, decay_steps, decay_rate):
        super().__init__()
        self.initial_learning_rate = tf.cast(initial_learning_rate, dtype=tf.float32)
        self.decay_steps = tf.cast(decay_steps, dtype=tf.float32)
        self.decay_rate = tf.cast(decay_rate, dtype=tf.float32)

    def __call__(self, step):
        return self.initial_learning_rate * tf.math.exp(-self.decay_rate * (step / self.decay_steps))

class Blenderbot(tf.keras.Model):
    def __init__(self):
        super().__init__()
        self.b_model = b_model

    def get_b_model(self):
        return self.b_model

    def call(self, input_ids=None,
        attention_mask=None,
        decoder_input_ids=None,
        decoder_attention_mask=None,
        training=None, **kwargs):

        lm_logits = self.b_model(input_ids=input_ids, attention_mask=attention_mask, decoder_input_ids=decoder_input_ids, decoder_attention_mask=decoder_attention_mask, training=training).logits

        return lm_logits

def train():
    model = Blenderbot()
    batch_size = 12
    epoch = 100

    inputs = create_inputs_labels("data/train_data.txt", 5000)

    dataset = ({
            'input_ids': inputs["input_ids"],
            'decoder_input_ids': inputs["decoder_input_ids"][:, :-1],
            'attention_mask': inputs["attention_mask"],
            'decoder_attention_mask': inputs["decoder_attention_mask"][:, :-1],
            }, inputs["decoder_input_ids"][:, 1:])

    train_dataset = tf.data.Dataset.from_tensor_slices(dataset)
    train_dataset = train_dataset.shuffle(1000).batch(batch_size)

    total_steps = inputs["input_ids"].shape[0] // batch_size * epoch
    print("总步数：", total_steps)
    natural_exp_decay = NaturalExpDecay(initial_learning_rate=4e-5,
                                        decay_steps=total_steps,
                                        decay_rate=1e-6)

    optimizer = tf.keras.optimizers.Adam(natural_exp_decay)

    # model.compile(optimizer=optimizer, loss=tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True, reduction=tf.keras.losses.Reduction.NONE), metrics=["accuracy"])
    model.compile(optimizer=optimizer, loss=compute_loss, metrics=accuracy)
    # model.summary()

    train_call = tf.keras.callbacks.ModelCheckpoint("models.h5", monitor='loss', verbose=0, save_best_only=False,
                                                 save_weights_only=True, mode='auto', period=3)

    model.fit(train_dataset, epochs=epoch, callbacks=[train_call])



if __name__ == '__main__':
    train()
