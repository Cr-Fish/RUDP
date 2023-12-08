import sys
import getopt

import Checksum
import BasicSender
import Checksum
import BasicSender
import base64
import time

'''
This is a skeleton sender class. Create a fantastic transport protocol here.
'''
class Sender(BasicSender.BasicSender):
    def __init__(self, dest, port, filename, debug=False, sackMode=False):
        super(Sender, self).__init__(dest, port, filename, debug)
        self.sackMode = sackMode
        self.PacketDataSize = 1000  # packet size
        self.win_size = 5 # 发送窗口大小
        self.window = dict() # 发送窗口
        self.timeout = 0.5 
        self.seqno = 0
        self.MaxAck = 0
        self.end = False
        self.finished = False # 记录是否传输完成
        self.LastSendTime = time.time()
        self.acks = [] # 用于选择重传，记录选择的确认


    # 发送窗口中的所有包
    def send_window(self):
        for key,value in self.window.items():
            if int(key) >= self.MaxAck:
                self.send("{}".format(value))


    # 获取整个窗口
    def get_window(self):
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


    # 接收函数，处理ack
    def receive_ack(self):
        self.LastSendTime = time.time()
        for _ in range(len(self.window)):
            if time.time() - self.LastSendTime > self.timeout: # handle timeout
                break
            
            # 接收
            response = self.receive(self.timeout/2)
            if response == None:
                continue
            response = response.decode()
            
            if Checksum.validate_checksum(response)==False: # 校验和无效，丢弃
                continue
            
            msg_type, seqno, data, checksum = self.split_packet(response)
            if(self.sackMode): # sack
                seqno_split = seqno.split(';') # seqno: <cum_ack;sack1,sack2,sack3,...>
                cum_ack = seqno_split[0]
                sacks = seqno_split[1]
                if int(cum_ack) > self.MaxAck: 
                    self.MaxAck = int(cum_ack)
                
                acks = sacks.split(',')
                for ack in acks:
                    if ack != '':
                        self.acks.append(int(ack)) # 加入acks列表
                        
            else: # go back n
                if int(seqno) > self.MaxAck:
                    self.MaxAck = int(seqno)


    # 处理发送窗口
    def ack_received(self):
        if(self.sackMode): # sack，需要从window中删除maxack之前的包和之后已经确认的包
            keys_to_remove = [key for key in self.window if int(key) < self.MaxAck or int(key) in self.acks]
            self.acks.clear()
        else: # go back n，只需删除maxack之前的包
            keys_to_remove = [key for key in self.window if int(key) < self.MaxAck]
        
        for key in keys_to_remove:
            del self.window[key]


    # 发送循环
    def start(self):
        resend = False
        while self.finished == False:  # 循环发送文件，如果传送完成则退出循环
            if(resend):
                self.ack_received()
            
            self.get_window()
            self.send_window()
            
            self.receive_ack()
            
            # 检查是否需要重传
            if(self.MaxAck < self.seqno): # 有包丢失，需要重传
                resend = True
            else:
                resend = False
                self.window.clear() # 不需要重传，清空发送窗口
            
            if(self.end and len(self.window) == 0): # 传输完成
                self.finished = True

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
