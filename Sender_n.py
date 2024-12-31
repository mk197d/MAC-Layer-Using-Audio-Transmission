import pyaudio
import numpy as np
import time
import random
from datetime import datetime

from CONSTANTS import SRC_NODE, EXTRA_END_BITS
from CONSTANTS import sample_rate, volume, bit_duration, chunk_size
from CONSTANTS import f_0, f_1, f_d, tolerance
from CONSTANTS import CW_MAX, CW_MIN, SIFS, DIFS, SLOT_DURATION
from CONSTANTS import RETURN_MESSAGE, START_BITS, END_BITS
from CONSTANTS import ACK_REC_TIMEOUT, ACK_SEND_TIME, RECEIVER_INIT_TIME
from CONSTANTS import CHECK_1, CHECK_2, CHECK_3




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

p_cs = pyaudio.PyAudio()
p_ack = pyaudio.PyAudio()
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

def receive_ack():
    """
    Receives an acknowledgment signal by listening to audio input and detecting specific frequencies 
    that encode the acknowledgment bits.

    Returns:
        bool: True if the acknowledgment message matches the expected bits, False otherwise.
    """

    print("Receiving Acknowledgement")
    
    stream_ack = p_ack.open(format=pyaudio.paInt16, channels=1, rate=sample_rate, input=True, frames_per_buffer=chunk_size)
    
    prev_time = time.time()     # Record the initial time to check timeouts
    
    # Loop for synchronizing to identify the start of message
    # by skipping the initial '1' bits of acknowledgement         
    while True:
        
        # If the time difference exceeds the DIFS interval, return False (timeout)
        if time.time() - prev_time > ACK_REC_TIMEOUT:
            return False
        
        data = stream_ack.read(chunk_size, exception_on_overflow=False)
        detected_freq = detect_frequency(data, sample_rate)
        matched_bit = match_frequency(detected_freq)
        
        # Updating the prev_time to latest time on which a bit was detected
        if matched_bit in [0, 1, 'delimiter']:
            prev_time = time.time()
        
        # The first '0' bit indicates that the preamble has ended
        if matched_bit == 0:
            break
     
    # Loop for skipping the extra '0' bits catched in the stream
    prevBit = 0
    while prevBit != 'delimiter':
        
        # If the time difference exceeds the DIFS interval, return False (timeout)
        if time.time() - prev_time > ACK_REC_TIMEOUT:
            return False
        
        data = stream_ack.read(chunk_size, exception_on_overflow=False)
        detected_freq = detect_frequency(data, sample_rate)
        matched_bit = match_frequency(detected_freq)
        
        # Updating the prev_time to latest time on which a bit was detected
        if matched_bit in [0, 1, 'delimiter']:
            prev_time = time.time()
            
        if matched_bit == 'delimiter':
            prevBit = 'delimiter'            
    
        
    decoded_bits = []   
    match_ack = RETURN_MESSAGE[5:-EXTRA_END_BITS]
    while decoded_bits != match_ack and len(decoded_bits) < len(match_ack):
        
        # If the time difference exceeds the DIFS interval, return False (timeout)
        if time.time() - prev_time > ACK_REC_TIMEOUT:
            return False
        
        data = stream_ack.read(chunk_size, exception_on_overflow=False)
        detected_freq = detect_frequency(data, sample_rate)
        matched_bit = match_frequency(detected_freq)
        
        # Updating the prev_time to latest time on which a bit was detected
        if matched_bit in [0, 1, 'delimiter']:
            prev_time = time.time()
        
        # Updating the prev_bit used for decoding RZ signal
        if matched_bit != prevBit:
            prevBit = matched_bit
            
            if prevBit in [0, 1]:
                decoded_bits.append(prevBit)
                print(f"ACK_BIT: {matched_bit}")
                
            elif prevBit == 'delimiter':
                pass
            
    
    stream_ack.close()
    
    if decoded_bits == RETURN_MESSAGE[5:-EXTRA_END_BITS]:
        'Return true if the decoded bits match the Acknowledgement with preamble removed'
        return True
    
    else:
        return False
            

##########################################################################################
########################################################################################## 

def carrier_sense(): 
    """
    Performs carrier sensing to check if the communication channel is busy by analyzing the frequency of incoming data.
    
    Reads audio data from the input stream, detects the frequency, and matches it to [f_0, f_1, or delimiter] to determine
    if a signal is present.
    
    Returns:
        bool: True if a signal (carrier) is detected on the channel, False otherwise.
    """
    
    stream_cs = p_cs.open(format=pyaudio.paInt16, channels=1, rate=sample_rate, input=True, frames_per_buffer=chunk_size)
    data = stream_cs.read(chunk_size, exception_on_overflow=False)
    stream_cs.close()
    
    detected_freq = detect_frequency(data, sample_rate)
    matched_bit = match_frequency(detected_freq)
    
    if matched_bit in [0, 1, 'delimiter']:
        return True
                
    return False


def sense_time(t):
    """
    Performs carrier sensing for a specified duration to detect if the channel is busy. 
    If a carrier (signal) is detected within the time interval, it flags a collision.

    Args:
        t (float): The duration (in seconds) to sense the channel for any carrier signal.
    
    Returns:
        bool: True immediately if a collision occurs within the time period, False otherwise.
    """
    
    collision = False
            
    start_time = time.time()
    while time.time() - start_time < t:
        if carrier_sense():
            collision = True
            break
            
    return collision
        

def csma_transmit(message, dest):
    """
    Transmits a message using the CSMA/CA protocol with carrier sensing and collision avoidance.
    
    The function senses the medium for availability, performs a random backoff, and transmits 
    the message. It listens for acknowledgment (ACK) from the destination to confirm successful transmission.
    
    Args:
        message (list): The message to be transmitted, represented as a list of bits (0s and 1s).
        dest (list): The destination address (if [0, 0], it indicates multiple recipients).
    
    Returns:
        str: A timestamp of when the message was successfully transmitted, if acknowledged.
    """
    
    global MESSAGE_COUNT
    
    send_message = add_count(message, MESSAGE_COUNT)
    send_message = add_start_end(send_message)
    contention_window = CW_MIN  # Start with the minimum contention window size
    
    ack1 = False
    ack2 = False
    
    # Continuously attempt to transmit the message until successful
    while True:
        
        'Step 1: Perform carrier sensing to check if the medium is free'
        if not carrier_sense():
            
            'Step 2: If the medium is free, sense the medium for DIFS duration'
            if sense_time(DIFS):
                continue    # If busy during DIFS, restart the process
            
            'Step 3: Perform random backoff if medium is free after DIFS'
            backoff_time_slots = random.randint(0, contention_window)
            print(f"DIFS-pass | Backoff Slots: {backoff_time_slots}")
                  
            # Count down the backoff time slots while continuously checking the medium  
            while backoff_time_slots > 0:      
                if not sense_time(SLOT_DURATION):
                    backoff_time_slots -= 1                    
                    
                else:     
                    pass
                    
            
            print("[DIFS + SLOTS]-pass")
            
            'Step 4: Sense the medium for SIFS (Short Inter-frame Space) duration before transmitting'
            if sense_time(SIFS):
                contention_window *= 2
                
                if contention_window > CW_MAX:
                    contention_window = CW_MIN  # Reset contention window if it exceeds maximum

                print(f"MEDIUM BUSY | WHEN READY TO TRANSMIT | CW = {contention_window}")                        
                continue    # Go back and retry
            
            
            'Step 5: Construct the signal (frequencies and durations) for the message transmission'
            frequencies = []
            durations = []
            for bit in send_message:
                if bit == 1:
                    frequencies.append(f_1)
                else:
                    frequencies.append(f_0)
                
                durations.append(bit_duration)
                frequencies.append(f_d)  
                durations.append(bit_duration)
                        
            play_signal(frequencies, durations)
            
            
            # Get the current timestamp when the message is transmitted
            
            
            'Step 6: Wait for SIFS duration before checking for acknowledgment (ACK)'
            # time.sleep(SIFS)
            if dest != [0, 0]:  # If single destination
                ack = False
                ack = receive_ack()
            
                if ack:
                    timestamp = get_timestamp()
                    return timestamp
                
                else:
                    print("ACK not recieved") 
                        
            else:               # If broadcasting
                if ack1:
                    time.sleep(ACK_SEND_TIME)
                else:
                    ack1 = receive_ack()    # Receive ACK from the first destination
                
                time.sleep(RECEIVER_INIT_TIME)
                
                if not ack2:
                    ack2 = receive_ack()    # Receive ACK from the second destination
                else:
                    time.sleep(ACK_SEND_TIME)
                    
                    
                if ack1 and ack2:       # Check if both ACKs are received
                    timestamp = get_timestamp()
                    return timestamp
                
                else:
                    print(f"ACK1: {ack1} and ACK2: {ack2} not received") 
               
        else:
            pass
                
##########################################################################################
##########################################################################################

def add_start_end(message):
    """Adds start and end bit sequences to the message."""
    
    final_message = []
    final_message.extend(START_BITS)
    final_message.extend(message)
    final_message.extend(END_BITS)

    return final_message

def bit_stuff(message):
    """Inserts a '1' after four consecutive '0's in the message for bit stuffing."""
    
    i = 0
    ret_message = []
    ret_message.extend(message)
    while i <= len(ret_message) - 4:
        
        if ret_message[i:i+4] == [0, 0, 0, 0]:
            ret_message.insert(i + 4, 1)
            i += 5
            
        else:
            i += 1
            
    return ret_message

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


def add_header(message, dest):
    """Adds a header containing source and destination node information to the message."""
    
    ret_message = []
    
    if SRC_NODE == [0, 1]:
        ret_message.extend(CHECK_1)
        
    elif SRC_NODE == [1, 0]:
        ret_message.extend(CHECK_2)
        
    elif SRC_NODE == [1, 1]:
        ret_message.extend(CHECK_3)
        
    ret_message.extend(SRC_NODE)
    ret_message.extend(dest)
    ret_message.extend(message)
    
    return ret_message

def add_count(message, cnt):
    
    binary_number = bin(cnt)[2:].zfill(3) 
    binary_list = [int(bit) for bit in binary_number]    
    new_list = binary_list + message
    
    return new_list
    
def transform_message(message, dest):
    """Applies header, bit stuffing, and start/end bits to the message."""
    ret_message = (add_header(bit_stuff(message), dest))
    return ret_message

##########################################################################################
##########################################################################################

def read_message_file(file_path):
    """Reads a message file and returns a list of destination-message pairs as binary lists."""
    
    pairs = []
    with open(file_path, 'r') as file:
        for line in file:
            message, dest = line.strip().split()
            
            message_bits = [int(bit) for bit in message]
            
            if dest == '-1':
                pairs.append((-1, message_bits))
            
            else:
                dest_binary = [int(bit) for bit in format(int(dest), '02b')]
                pairs.append((dest_binary, message_bits))
                        
    return pairs

def process_messages(pairs):
    """Processes each destination-message pair by transmitting the message and printing the timestamp."""

    for dest, message in pairs:
        
        input("Press Enter to continue...")
        global MESSAGE_COUNT
        MESSAGE_COUNT += 1
        if dest != -1:
            timeStamp = csma_transmit(transform_message(message, dest), dest)  
            with open('send.txt', 'a') as file:
                file.write(f"[SENT]: {message} {decimal_value(dest)} {timeStamp}\n")              
                print(f"[SENT]: {message} {decimal_value(dest)} {timeStamp}")
       

##########################################################################################
########################################################################################## 


MESSAGE_COUNT = 0

file_path = "messages.txt"  
message_pairs = read_message_file(file_path)

process_messages(message_pairs)

p_p.terminate()
p_ack.terminate()
p_cs.terminate()
