
SRC_NODE = [1, 0]

sample_rate = 44100 
volume = 1.0   
bit_duration = 0.2

chunk_size = int(sample_rate * bit_duration)

f_0 = 440
f_1 = 1320
f_d = 880
tolerance = 50
  
CW_MIN = 4
CW_MAX = 1024
SIFS = 0.3
DIFS = 1.5
SLOT_DURATION = 1

EXTRA_END_BITS = 1

CHECK_1 = [0, 0, 1, 1]
CHECK_2 = [1, 1, 0, 0]
CHECK_3 = [0, 1, 1, 0]

RETURN_MESSAGE = [1, 1, 1, 1, 0, 1, 0, 0, 0, 1, 1]
START_BITS = [0, 0, 0, 0, 0, 1]

END_BITS = [0, 0, 0, 0, 0, 1, 1]
REC_END_BITS = END_BITS[:-EXTRA_END_BITS]

SENDER_INIT_TIME = 1
RECEIVER_INIT_TIME = 0.5

ACK_SEND_INIT = 1
ACK_SEND_TIME = 6.4

REC_TIMEOUT = 1.5
ACK_REC_TIMEOUT = 1.5
