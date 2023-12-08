import sys
import getopt

import Checksum
import BasicSender
import Checksum
import BasicSender
import base64
import time
from copy import deepcopy

'''
This is a skeleton sender class. Create a fantastic transport protocol here.
'''
class Sender(BasicSender.BasicSender):
    def __init__(self, dest, port, filename, debug=False, sackMode=False):
        super(Sender, self).__init__(dest, port, filename, debug)
        self.sackMode = sackMode
        self.PacketDataSize = 500  # packet size
        self.win_size = 5 # 发送窗口大小
        self.window = dict() # 发送窗口
        self.timeout = 0.5 # timeout时间
        self.seqno = 0
        self.MaxAck = 0
        self.end = False
        self.LastSendTime = time.time()
        self.acks = [] # 用于选择重传，记录选择的确认

    '''
    思路:维护一个大小为BufSize的缓冲区,实现(通过dict):{seqno,packet}
    (1)开始时，把缓冲区读满，发送全部内容，然后接受ACK，检查接收的最大ACK是否满足预期。正确则开始下一轮，否则超时:
    (2)超时处理:分为GBN和SR两种方式，共同点是根据接收到TimeOut时间内接受的信息更新缓冲区(删掉被确认的部分信息，重
    新用需要发送的信息填满缓冲区)，发送、接受ACK，检查接收的最大ACK是否满足预期，不满足则继续超时处理。

    总结以上两个方面，具体实现为一个大while循环，每次开始时构造缓冲区Buf，构造方式分别为无错、GBN、SR，后两种构造方式
    对应超时重传。构造完成后，将缓冲区内容发送、等待接受，然后检查是否有错，继续循环。
    '''
    # Main sending loop.
    def fill_window(self):
        while len(self.window) < self.win_size and self.end == False: # 循环发送文件，直到窗口满或文件结束
            msg = self.infile.read(self.PacketDataSize) # 读取接受到的数据
            msg = base64.b64encode(msg).decode() # 编码???
            
            # 根据情况选择类型后make_packet
            if(self.seqno == 0): # 第一个包
                packet = self.make_packet('start', self.seqno, msg) # 打包成start包
            elif(msg == '' or msg == ""): # 通过msg是否为空判断是否为最后一个包
                packet = self.make_packet('end', self.seqno, msg) # 打包成end
                self.end = True # 标记最后一个包，以便其他函数使用
            else: # 中间的数据包
                packet = self.make_packet('data', self.seqno, msg) # 打包成data包
            
            self.window.update({self.seqno: packet}) # 将当前的包加入发送窗口
            self.seqno += 1

    def go_back_n(self):
        # 删除window中seqno < MaxAck的包
        keys_to_remove = [key for key in self.window if int(key) < self.MaxAck]
        for key in keys_to_remove:
            del self.window[key]
        self.fill_window()
    
    def sack(self):
        # 删除window中seqno < MaxAck的包、收到ack的包
        keys_to_remove = [key for key in self.window if int(key) < self.MaxAck or int(key) in self.acks]
        for key in keys_to_remove:
            del self.window[key]
        
        self.acks.clear() # 清空acks保证下次循环时不会重复删除
        self.fill_window()
    

    def start(self):
        REsendTag = False
        while True:
            # build BUf
            if(REsendTag == False):
                self.fill_window()
            else:
                if(self.sackMode):
                    self.sack()
                else:
                    self.go_back_n()
            # send BUf
            for key,value in self.window.items():
                if int(key) < self.MaxAck:
                    continue
                # debug: print("send:",key)
                self.send("{}".format(value))
            # receive answer
            i = 1
            self.LastSendTime = time.time()
            while i <= len(self.window):
                if time.time() - self.LastSendTime > self.timeout: # handle timeout
                    break
                try:
                    response = self.receive(self.timeout/2)
                except:
                    continue
                i += 1
                if response == None:
                    continue
                response = response.decode()
                if not Checksum.validate_checksum(response):
                    continue
                msg_type, seqno, data, checksum = self.split_packet(response)
                if(self.sackMode == False):
                    # 不使用选择重传
                    if int(seqno) > self.MaxAck:
                        self.MaxAck = int(seqno)
                else:
                    # 选择重传
                    seqno_split = seqno.split(';') # seqno: <cum_ack;sack1,sack2,sack3,...>
                    cum_ack = seqno_split[0]
                    sacks = seqno_split[1]
                    if int(cum_ack) > self.MaxAck: 
                        self.MaxAck = int(cum_ack)
                    # '选择确认'加入列表self.acks:
                    try:
                        acks = sacks.split(',')
                        for ack in acks:
                            self.acks.append(int(ack))  
                    except:
                        continue  
                    
            # 检查是否需要重传，设置REsendTag
            if(self.MaxAck < self.seqno):
                REsendTag = True
            else:
                REsendTag = False
                self.window.clear()
            if(self.end and len(self.window) == 0):
                break
        self.infile.close()


    def handle_timeout(self):
        pass

    def handle_new_ack(self, ack):
        pass

    def handle_dup_ack(self, ack):
        pass

    def log(self, msg):
        if self.debug:
            print(msg)


'''
This will be run if you run this script from the command line. You should not
change any of this; the grader may rely on the behavior here to test your
submission.
'''
if __name__ == "__main__":
    def usage():
        print("RUDP Sender")
        print("-f FILE | --file=FILE The file to transfer; if empty reads from STDIN")
        print("-p PORT | --port=PORT The destination port, defaults to 33122")
        print("-a ADDRESS | --address=ADDRESS The receiver address or hostname, defaults to localhost")
        print("-d | --debug Print debug messages")
        print("-h | --help Print this usage message")
        print("-k | --sack Enable selective acknowledgement mode")

    try:
        opts, args = getopt.getopt(sys.argv[1:],
                               "f:p:a:dk", ["file=", "port=", "address=", "debug=", "sack="])
    except:
        usage()
        exit()

    port = 33122
    dest = "localhost"
    filename = None
    debug = False
    sackMode = False

    for o,a in opts:
        if o in ("-f", "--file="):
            filename = a
        elif o in ("-p", "--port="):
            port = int(a)
        elif o in ("-a", "--address="):
            dest = a
        elif o in ("-d", "--debug="):
            debug = True
        elif o in ("-k", "--sack="):
            sackMode = True

    s = Sender(dest, port, filename, debug, sackMode)
    try:
        s.start()
    except (KeyboardInterrupt, SystemExit):
        exit()
