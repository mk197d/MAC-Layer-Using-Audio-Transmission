import pyaudio
import numpy as np
import time

from datetime import datetime

from CONSTANTS import SRC_NODE
from CONSTANTS import sample_rate, volume, bit_duration, chunk_size
from CONSTANTS import f_0, f_1, f_d, tolerance
from CONSTANTS import CW_MAX, CW_MIN, SIFS, DIFS, SLOT_DURATION
from CONSTANTS import RETURN_MESSAGE, REC_END_BITS, EXTRA_END_BITS
from CONSTANTS import SENDER_INIT_TIME, ACK_SEND_TIME, ACK_SEND_INIT
from CONSTANTS import ACK_REC_TIMEOUT, REC_TIMEOUT
from CONSTANTS import CHECK_1, CHECK_2, CHECK_3

##########################################################################################
##########################################################################################

RECEIVED_SET = set()

##########################################################################################
##########################################################################################
def get_timestamp():
    """
    Fetches the current time which is synchronized for all the nodes beforehand.
    """

    timestamp = datetime.now().strftime('%H:%M:%S')
    return timestamp

def decimal_value(length_bits):
    'Returns the decimal value represented by the given binary list'
    
    decimal_value = 0
    for i, bit in enumerate(reversed(length_bits)):
        decimal_value += bit * (2 ** i)

    return decimal_value


##########################################################################################
##########################################################################################

p_rc = pyaudio.PyAudio()
p_p = pyaudio.PyAudio()

def generate_tone(frequency, duration, sample_rate):
    """
    Generates a sine wave tone of a specified frequency and duration.

    Args:
        frequency (float): The frequency of the tone in Hertz.
        duration (float): The duration of the tone in seconds.
        sample_rate (int): The sample rate in samples per second, used for generating the tone.

    Returns:
        numpy.ndarray: A NumPy array containing the generated tone as a float32 data type.
    """
    
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    tone = np.sin(frequency * t * 2 * np.pi) * volume
    return tone.astype(np.float32)


def play_signal(frequencies, durations): 
    """
    Plays a sequence of audio signals corresponding to a list of frequencies and durations.

    Args:
        frequencies (list): A list of frequencies in Hertz for each tone to be played.
        durations (list): A list of durations in seconds corresponding to each frequency.
    """
           
    stream_p = p_p.open(format=pyaudio.paFloat32, channels=1, rate=sample_rate, output=True)
    
    for frequency, duration in zip(frequencies, durations):
        tone = generate_tone(frequency, duration, sample_rate)
        stream_p.write(tone.tobytes())    
        
    stream_p.close()


##########################################################################################
##########################################################################################
   
def detect_frequency(data, sample_rate):
    """
    Detects the dominant frequency in an audio signal using the Fast Fourier Transform (FFT).

    Args:
        data (bytes): Audio signal data, typically in a buffer.
        sample_rate (int): The sample rate of the audio signal in samples per second.

    Returns:
        float: The dominant frequency present in the audio signal.
    """
    
    data = np.frombuffer(data, dtype=np.int16)
    fft_result = np.fft.fft(data)
    freqs = np.fft.fftfreq(len(fft_result), 1 / sample_rate)
    
    idx = np.argmax(np.abs(fft_result[:len(fft_result)//2])) 
    peak_freq = abs(freqs[idx])
    
    return peak_freq    
    
    
def match_frequency(freq):
    """
    Matches a detected frequency to predefined frequencies (f_0, f_1, f_d) within a tolerance range.

    Args:
        freq (float): The detected frequency in Hertz to be matched.
    """
    
    if abs(freq - f_0) < tolerance:
        return 0
    elif abs(freq - f_1) < tolerance:
        return 1
    elif abs(freq - f_d) < tolerance:
        return 'delimiter'
    return -1


##########################################################################################
##########################################################################################

def remove_bit_stuffing(message):
    """Removes the inserted '1' from bit-stuffed message."""
    
    i = 5
    extra_bits = []
    while i <= len(message):  
        if message[i-5 : i] == [0, 0, 0, 0, 1]:
            extra_bits.append(i - 1)
            
        i += 1
    
    i = 0
    ret_message = []
    while i < len(message):
        if i not in extra_bits:
            ret_message.append(message[i])
            
        i += 1
            
    return ret_message

##########################################################################################
##########################################################################################

def already_received(count_bits, sender_bits):
    add_bits = tuple(sender_bits + count_bits)
    
    if add_bits in RECEIVED_SET:
        return True
    
    else:
        RECEIVED_SET.add(add_bits)
        return False

def transmit_rc(message):
    """Transmits an acknowledgment signal based on the given message bits."""
    
    print(f"Transmitting Acknowledgement")
    
    frequencies = []
    durations = []
    for bit in message:
        if bit == 1:
            frequencies.append(f_1)
        else:
            frequencies.append(f_0)
        
        durations.append(bit_duration)
        frequencies.append(f_d)  
        durations.append(bit_duration)
                    
    play_signal(frequencies, durations)


def receive_messages():
    """Continuously listens for incoming messages, decodes them, and responds if applicable."""
    
    while True:
        stream_rc = p_rc.open(format=pyaudio.paInt16, channels=1, rate=sample_rate, input=True, frames_per_buffer=chunk_size)
        
        prev_time = time.time()  # Record the time when listening starts
        error = False  # Flag to indicate if an error occurs during reception
        
        'Loop to synchronize the receiver and skip the preamble'
        while True:
            
            'Check for a timeout; if it exceeds DIFS, set error flag and break'
            if time.time() - prev_time > REC_TIMEOUT:
                error = True
                break
                
            data = stream_rc.read(chunk_size, exception_on_overflow=False)
            detected_freq = detect_frequency(data, sample_rate) 
            matched_bit = match_frequency(detected_freq)
            
            'Updating the prev_time to latest time when a bit was detected'
            if matched_bit in [0, 1, 'delimiter']:
                prev_time = time.time()
            
            if matched_bit == 1:
                break
        
        'Skip the loop if Timeout has occoured'    
        if error:
            continue
           
        prevBit = 1     # Loop to skip the extra '1' bits in the stream which are part of preamble
        while prevBit != 'delimiter':
            
            'Check for a timeout; if it exceeds DIFS, set error flag and break'
            if time.time() - prev_time > REC_TIMEOUT:
                error = True
                break
            
            data = stream_rc.read(chunk_size, exception_on_overflow=False)
            detected_freq = detect_frequency(data, sample_rate)
            matched_bit = match_frequency(detected_freq)
            
            'Updating the prev_time to latest time when a bit was detected'
            if matched_bit in [0, 1, 'delimiter']:
                prev_time = time.time()
            
            if matched_bit == 'delimiter':
                prevBit = 'delimiter'  


        'Skip the loop if Timeout has occoured'            
        if error:
            continue
        
        
        'Continue reading bits until the auxiliary bits are detected at the end'
        decoded_bits = []
        while decoded_bits[-len(REC_END_BITS):] != REC_END_BITS:
            
            'Check for a timeout; if it exceeds DIFS, set error flag and break'
            if time.time() - prev_time > REC_TIMEOUT:
                error = True
                break
            
            data = stream_rc.read(chunk_size, exception_on_overflow=False)
            detected_freq = detect_frequency(data, sample_rate)
            matched_bit = match_frequency(detected_freq)
            
            'Updating the prev_time to latest time when a bit was detected'
            if matched_bit in [0, 1, 'delimiter']:
                prev_time = time.time()
                
            if matched_bit != prevBit:
                prevBit = matched_bit
                
                if prevBit in [0, 1]:
                    decoded_bits.append(prevBit)
                    print(f"RCV_BIT: {matched_bit}")
                    
                elif prevBit == 'delimiter':
                    # print("RCV_DEL")
                    pass
         
        'Skip the loop if Timeout has occoured' 
        if error:
            continue          
         
        stream_rc.close()
                          
        if len(decoded_bits) < (11 + len(REC_END_BITS) - EXTRA_END_BITS):
            continue
         
        # Extract sender and receiver bits from the decoded bits
        count_bits = decoded_bits[:3]
        check_bits = decoded_bits[3:7]
        sender_bits = decoded_bits[7:9]  # First two bits are sender ID
        receiver_bits = decoded_bits[9:11]  # Next two bits are receiver ID
        
        message_bits = (decoded_bits[11:-len(REC_END_BITS)])  # Extract the actual message bits
        message_bits = remove_bit_stuffing(message_bits)  # Remove any bit stuffing from the message
        
        if sender_bits == [0, 1] and check_bits == CHECK_1:
            print("RECEIVING FROM 1")
            
        elif sender_bits == [1, 0] and check_bits == CHECK_2:
            print("RECEIVING FROM 2")
            
        elif sender_bits == [1, 1] and check_bits == CHECK_3:
            print("RECEIVING FROM 3")
            
        else:
            print("UNIDENTIFIED SENDER")
            continue
        
        # Check if the receiver bits match the source node
        if receiver_bits == SRC_NODE:
            time.sleep(ACK_SEND_INIT)
            transmit_rc(RETURN_MESSAGE)

         # Check if the receiver bits indicate a broadcast to all nodes
        elif receiver_bits == [0, 0] and sender_bits != SRC_NODE:
            if SRC_NODE == [0, 1]:
                time.sleep(SENDER_INIT_TIME)
                transmit_rc(RETURN_MESSAGE)
                
            elif SRC_NODE == [1, 0]:
                if sender_bits == [0, 1]:
                    time.sleep(SENDER_INIT_TIME)
                    transmit_rc(RETURN_MESSAGE)
                    
                elif sender_bits == [1, 1]:
                    time.sleep(ACK_SEND_TIME)
                    transmit_rc(RETURN_MESSAGE)   
                    
            else:
                time.sleep(ACK_SEND_TIME)
                transmit_rc(RETURN_MESSAGE)  
            
        
        timestamp = get_timestamp()
        
        if (receiver_bits == SRC_NODE or (receiver_bits == [0, 0] and sender_bits != SRC_NODE)) and not already_received(count_bits, sender_bits):
            with open('receive.txt', 'a') as file:
                file.write(f"[RECVD]: {message_bits} {decimal_value(sender_bits)} {timestamp}\n")
                
            print(f"[RECVD]: {message_bits} {decimal_value(sender_bits)} {timestamp}")
            

##########################################################################################
########################################################################################## 

RECEIVED_SET = set()
receive_messages()

p_rc.terminate()
p_p.terminate()
