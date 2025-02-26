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

    def on_login(self, err_code):
        """ 로그인 이벤트 처리 """
        if err_code == 0:
            print("✅ 키움증권 모의투자 로그인 성공")
        else:
            print(f"❌ 로그인 실패 (코드: {err_code})")
        self.app.quit()

    def get_mock_account(self):
        """ 모의투자 계좌 가져오기 """
        accounts = self.kiwoom.dynamicCall("GetLoginInfo(QString)", "ACCNO").split(';')
        self.account = accounts[0]
        print(f"🏦 모의투자 계좌번호: {self.account}")

    # 🚀 거래량 급등 & 등락률 상위 종목 조회
    def get_filtered_stocks(self):
        self.get_mock_account()
        self.filtered_stocks = []

        self.kiwoom.dynamicCall("SetInputValue(QString, QString)", "시장구분", "000")
        self.kiwoom.dynamicCall("CommRqData(QString, QString, int, QString)", "거래량급등요청", "opt10030", 0, "0101")

        self.kiwoom.OnReceiveTrData.connect(self.on_receive_filtered_stocks)
        self.app.exec_()

        self.filtered_stocks = [code for code in self.filtered_stocks if code.strip()]
        print("\n✅ 최종 필터링된 종목 목록:", self.filtered_stocks)
        return self.filtered_stocks

    def on_receive_filtered_stocks(self, scr_no, rq_name, tr_code, record_name, prev_next):
        """ 거래량 급등 & 등락률 상위 종목 응답 처리 """
        count = self.kiwoom.dynamicCall("GetRepeatCnt(QString, QString)", tr_code, rq_name)
        for i in range(count):
            code = self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, i, "종목코드").strip()
            self.filtered_stocks.append(code)
        self.app.quit()

    def get_current_price(self, code):
        """ 현재 주가 가져오기 """
        self.kiwoom.dynamicCall("SetInputValue(QString, QString)", "종목코드", code)
        self.kiwoom.dynamicCall("CommRqData(QString, QString, int, QString)", "현재가조회", "opt10001", 0, "0101")

        self.kiwoom.OnReceiveTrData.connect(self.on_receive_price_data)
        self.app.exec_()
        return self.current_price

    def on_receive_price_data(self, scr_no, rq_name, tr_code, record_name, prev_next):
        """ 현재가 응답 처리 """
        self.current_price = int(self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, 0, "현재가").strip())
        self.app.quit()

    def get_stock_data(self, code):
        """ 📊 종목의 5일선 & 20일선 데이터 가져오기 """
        self.kiwoom.dynamicCall("SetInputValue(QString, QString)", "종목코드", code)
        self.kiwoom.dynamicCall("CommRqData(QString, QString, int, QString)", "주식일봉차트조회", "opt10081", 0, "0101")

        self.kiwoom.OnReceiveTrData.connect(self.on_receive_stock_data)
        self.data = []
        self.app.exec_()

        df = pd.DataFrame(self.data, columns=['date', 'close'])
        df['close'] = df['close'].astype(int)
        df['5MA'] = df['close'].rolling(window=5).mean()
        df['20MA'] = df['close'].rolling(window=20).mean()
        
        return df

    def on_receive_stock_data(self, scr_no, rq_name, tr_code, record_name, prev_next):
        """ 📊 주가 데이터 처리 """
        count = self.kiwoom.dynamicCall("GetRepeatCnt(QString, QString)", tr_code, rq_name)
        for i in range(count):
            date = self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, i, "일자").strip()
            close = self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, i, "현재가").strip()
            self.data.append([date, close])
        self.app.quit()

    def check_exit_conditions(self, code, entry_price):
        """ 매도 조건 체크 """
        current_price = self.get_current_price(code)
        profit_rate = (current_price - entry_price) / entry_price * 100  

        if profit_rate >= 10:  
            print(f"🎯 {code} 목표 수익률 {profit_rate:.2f}% 도달! 매도 실행")
            self.send_order(code, -1)
            return True  

        if profit_rate <= -3:  
            print(f"🚨 {code} 손실 {profit_rate:.2f}% 발생! 손절 매도")
            self.send_order(code, -1)
            return True  

        df = self.get_stock_data(code)
        if len(df) < 20:
            return False  

        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]

        if prev_row['5MA'] > prev_row['20MA'] and last_row['5MA'] < last_row['20MA']:
            print(f"🚨 {code} 데드크로스 발생! 매도 실행")
            self.send_order(code, -1)
            return True  
        return False  

    def check_golden_cross(self, code):
        # 골든크로스 확인 후 매수 실행 """
        df = self.get_stock_data(code)
        if len(df) < 20:
            return False  # 데이터 부족 시 매수 안 함

        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]

        if prev_row['5MA'] < prev_row['20MA'] and last_row['5MA'] > last_row['20MA']:
            print(f"🚀 {code} 골든크로스 발생! 매수 실행")
            self.send_order(code, 1)  # 매수 실행
            return True  # 매수 성공
        return False  # 매수 조건 충족 안됨

    def run(self):
        """ 실시간 매매 실행 """
        stock_list = self.get_filtered_stocks()
        entry_prices = {}

        while True:
            for code in stock_list:
                if code not in entry_prices:
                    if self.check_golden_cross(code):
                        entry_prices[code] = self.get_current_price(code)
                else:
                    if self.check_exit_conditions(code, entry_prices[code]):
                        entry_prices.pop(code, None)  # 매도 후 목록에서 삭제
                        print(f"📢 {code} 매도 완료, 관리 목록에서 제거")

            time.sleep(60)

if __name__ == "__main__":
    trader = KiwoomTrader()
    trader.run()
