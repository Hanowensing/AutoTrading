import sys
import time
import pandas as pd
from PyQt5.QtWidgets import QApplication
from PyQt5.QAxContainer import QAxWidget

class KiwoomTrader:
    def __init__(self):
        """ 키움증권 API 연결 및 로그인 (모의투자 계좌) """
        self.app = QApplication(sys.argv)
        self.kiwoom = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        self.kiwoom.dynamicCall("CommConnect()")  # 로그인 요청
        self.kiwoom.OnEventConnect.connect(self.on_login)
        self.app.exec_()
        self.criteria = ["ATR", "Momentum", "Financial", "Trend", "Volume"]  # 제거 우선순위
        self.data = []

    def get_mock_account(self):
        """ 모의투자 계좌 가져오기 """
        accounts = self.kiwoom.dynamicCall("GetLoginInfo(QString)", "ACCNO").split(';')
        self.account = accounts[0]
        print(f"🏦 모의투자 계좌번호: {self.account}")

    def on_login(self, err_code):
        if err_code == 0:
            print("✅ 키움증권 모의투자 로그인 성공")
        else:
            print(f"❌ 로그인 실패 (코드: {err_code})")
        self.app.quit()

    def get_historical_data(self, code, start_date, end_date):
        """ 과거 일봉 데이터 가져오기 """
        self.kiwoom.dynamicCall("SetInputValue(QString,QString)", "종목코드", code)
        self.kiwoom.dynamicCall("SetInputValue(QString,QString)", "기준일자", end_date)
        self.kiwoom.dynamicCall("SetInputValue(QString,QString)", "수정주가구분", "1")
        self.kiwoom.dynamicCall("CommRqData(QString,QString,int,QString)", "주식일봉차트조회", "opt10081", 0, "0101")
        
        self.kiwoom.OnReceiveTrData.connect(self.on_receive_stock_data)
        self.data = []
        self.app.exec_()

        if not self.data:
            print(f"⚠️ {code} 데이터 없음!")
            return pd.DataFrame()

        df = pd.DataFrame(self.data, columns=['date', 'close'])
        df['close'] = df['close'].astype(int)
        df['5MA'] = df['close'].rolling(window=5).mean()
        df['20MA'] = df['close'].rolling(window=20).mean()
        df['50MA'] = df['close'].rolling(window=50).mean()
        df['200MA'] = df['close'].rolling(window=200).mean()
        return df[(df['date'] >= start_date) & (df['date'] <= end_date)]
    
    def on_receive_stock_data(self, scr_no, rq_name, tr_code, record_name, prev_next):
        """ 주가 데이터 수신 처리 """
        count = self.kiwoom.GetRepeatCnt(tr_code, rq_name)
        for i in range(count):
            date = self.kiwoom.GetCommData(tr_code, rq_name, i, "일자").strip()
            close = self.kiwoom.GetCommData(tr_code, rq_name, i, "현재가").strip()
            self.data.append([date, close])
        self.app.quit()
    
    def get_filtered_stocks(self):
        """ 거래량 급등 종목 조회 """
        self.get_mock_account()
        self.filtered_stocks = []
        self.kiwoom.dynamicCall("SetInputValue(QString, QString)", "시장구분", "000")
        self.kiwoom.dynamicCall("CommRqData(QString, QString, int, QString)", "거래량급등요청", "opt10030", 0, "0101")
        self.kiwoom.OnReceiveTrData.connect(self.on_receive_filtered_stocks)
        self.app.exec_()
        self.filtered_stocks = [code for code in self.filtered_stocks if code.strip()]
        return self.filtered_stocks

    def on_receive_filtered_stocks(self, scr_no, rq_name, tr_code, record_name, prev_next):
        """ 거래량 급등 & 등락률 상위 종목 응답 처리 """
        count = self.kiwoom.GetRepeatCnt(tr_code, rq_name)
        for i in range(count):
            code = self.kiwoom.GetCommData(tr_code, rq_name, i, "종목코드").strip()
            self.filtered_stocks.append(code)
        self.app.quit()

    def run(self):
        """ 종목 필터링 및 실행 """
        stock_list = self.get_filtered_stocks()
        print("\n✅ 최종 필터링된 종목 목록:", stock_list)

if __name__ == "__main__":
    trader = KiwoomTrader()
    trader.run()