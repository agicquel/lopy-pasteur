class Log:
    DEFAULT_FILE_LOG = "/flash/log"
    WRITE_FILE_LOG_FLAG = False

    @staticmethod
    def e(error):
        Log.writeLog("[ERROR]", error, Log.DEFAULT_FILE_LOG)

    @staticmethod
    def w(warning):
        Log.writeLog("[WARNING]", warning, Log.DEFAULT_FILE_LOG)

    @staticmethod
    def i(info):
        Log.writeLog("[INFO]", info, Log.DEFAULT_FILE_LOG)

    @staticmethod
    def writeLOG(text, file):
        Log.writeLog("", text, file)

    @staticmethod
    def writeLog(mode, text, file):
        #cd = "[" + datetime.datetime.now() + "]"
        log = mode + " : " + text
        print(log)
        if(Log.WRITE_FILE_LOG_FLAG):
            f = open(file, 'w+')
            f.write(log)
            f.close
