import sys
import time
import pandas as pd
from PyQt5.QtWidgets import QApplication
from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtCore import QEventLoop

class KiwoomTrader:
    def __init__(self):
        """ 키움증권 API 연결 및 로그인 (모의투자 계좌) """
        self.app = QApplication(sys.argv)
        self.kiwoom = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        # 로그인 완료까지 기다리기 위한 별도 이벤트 루프 생성
        self.login_loop = QEventLoop()
        self.kiwoom.OnEventConnect.connect(self.on_login)
        self.kiwoom.dynamicCall("CommConnect()")  # 로그인 요청
        self.login_loop.exec_()  # 로그인 완료될 때까지 대기

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
        self.login_loop.quit()  # 로그인 이벤트 루프 종료

    # 이하의 메서드들은 기존 코드와 동일하며, 각 API 호출마다 QEventLoop를 사용합니다.
    def get_historical_data(self, code, start_date, end_date):
        """ 과거 일봉 데이터 가져오기 (최소 30일 전 데이터 필요) """
        self.kiwoom.dynamicCall("SetInputValue(QString,QString)", "종목코드", code)
        self.kiwoom.dynamicCall("SetInputValue(QString,QString)", "기준일자", end_date)
        self.kiwoom.dynamicCall("SetInputValue(QString,QString)", "수정주가구분", "1")
        self.kiwoom.dynamicCall("CommRqData(QString,QString,int,QString)", 
                                "주식일봉차트조회", "opt10081", 0, "0101")

        loop = QEventLoop()
        handler = lambda *args: (self.on_receive_stock_data(*args), loop.quit())
        self.kiwoom.OnReceiveTrData.connect(handler)
        self.data = []
        loop.exec_()
        self.kiwoom.OnReceiveTrData.disconnect(handler)

        print(f"{code} 종목 데이터 개수: {len(self.data)}")
        print(self.data[:5])

        if not self.data:
            print(f"⚠️ {code} 데이터 없음!")
            return pd.DataFrame()

        df = pd.DataFrame(self.data, columns=['date', 'close'])
        df['close'] = df['close'].astype(int)
        df['5MA'] = df['close'].rolling(window=5).mean()
        df['20MA'] = df['close'].rolling(window=20).mean()

        return df[(df['date'] >= start_date) & (df['date'] <= end_date)]

    def run_backtest(self, stock_list, start_date_for_data="20250101", 
                     start_date_for_backtest="20250201", end_date="20250225"):
        """ 백테스트 실행 """
        print(f"📊 백테스트 실행 시작 ({len(stock_list)}개 종목)")
        entry_prices = {}  # 매수한 종목 및 들어간 가격 저장
        profit_log = []    # 각 거래의 수익률 기록
        backtested_stocks_count = 0  # 데이터 충분해 백테스트 진행한 종목 수
        total_stocks_count = len(stock_list)  # 입력받은 종목 총 개수

        for code in stock_list:
            try:
                df = self.get_historical_data(code, start_date_for_data, end_date)
                print(f"📌 {code} 백테스트 진행 중")
                if df.empty or len(df) < 20:
                    print(f"⚠️ {code} 데이터 부족으로 스킵 (총 데이터 개수: {len(df)})")
                    continue
                backtested_stocks_count += 1

                # 백테스트 시작 날짜 이후 데이터만 사용
                df = df[df['date'] >= start_date_for_backtest]

                for i in range(1, len(df)):
                    prev_row = df.iloc[i - 1]
                    last_row = df.iloc[i]

                    if pd.isna(prev_row['5MA']) or pd.isna(prev_row['20MA']) or \
                       pd.isna(last_row['5MA']) or pd.isna(last_row['20MA']):
                        continue

                    print(f"🔎 {code} 날짜: {last_row['date']} 5MA: {last_row['5MA']}, 20MA: {last_row['20MA']}")

                    if prev_row['5MA'] < prev_row['20MA'] and last_row['5MA'] > last_row['20MA']:
                        entry_prices[code] = last_row['close']
                        print(f"✅ {last_row['date']} {code} 골든크로스 발생! 매수")

                    if code in entry_prices:
                        entry_price = entry_prices[code]
                        profit_rate = (last_row['close'] - entry_price) / entry_price * 100

                        if profit_rate >= 10:
                            print(f"🎯 {last_row['date']} {code} 목표 수익률 {profit_rate:.2f}% 도달! 매도")
                            profit_log.append(profit_rate)
                            del entry_prices[code]

                        elif profit_rate <= -3:
                            print(f"❌ {last_row['date']} {code} 손실 {profit_rate:.2f}% 발생! 손절 매도")
                            profit_log.append(profit_rate)
                            del entry_prices[code]

                        elif prev_row['5MA'] > prev_row['20MA'] and last_row['5MA'] < last_row['20MA']:
                            print(f"🚨 {last_row['date']} {code} 데드크로스 발생! 매도")
                            profit_log.append(profit_rate)
                            del entry_prices[code]

                print(f"📌 {code} 백테스트 종료, 수익 기록: {profit_log}")

            except Exception as e:
                print(f"❌ {code} 백테스트 중 오류 발생: {e}")
                continue

        print("\n📊 백테스트 완료!")
        print(f"🔍 입력받은 총 종목 수: {total_stocks_count}개")
        print(f"🔍 데이터가 충분해 백테스트 진행한 종목 수: {backtested_stocks_count}개")
        print(f"🔍 총 거래 횟수: {len(profit_log)}건")
        avg_profit = sum(profit_log) / len(profit_log) if profit_log else 0
        print("평균 수익률:", avg_profit, "%")

    def get_filtered_stocks(self):
        """ 거래량 급등 & 등락률 상위 종목 조회 """
        self.get_mock_account()
        self.filtered_stocks = []

        self.kiwoom.dynamicCall("SetInputValue(QString, QString)", "시장구분", "000")
        self.kiwoom.dynamicCall("CommRqData(QString, QString, int, QString)", 
                                "거래량급등요청", "opt10030", 0, "0101")

        loop = QEventLoop()
        handler = lambda *args: (self.on_receive_filtered_stocks(*args), loop.quit())
        self.kiwoom.OnReceiveTrData.connect(handler)
        loop.exec_()
        self.kiwoom.OnReceiveTrData.disconnect(handler)

        self.filtered_stocks = [code for code in self.filtered_stocks if code.strip()]
        print("\n✅ 최종 필터링된 종목 목록:", self.filtered_stocks)
        return self.filtered_stocks

    def on_receive_stock_data(self, *args):
        # 전달받은 인자 중 처음 5개만 사용합니다.
        scr_no, rq_name, tr_code, record_name, prev_next = args[:5]
        count = self.kiwoom.dynamicCall("GetRepeatCnt(QString, QString)", tr_code, rq_name)
        for i in range(count):
            date = self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)",
                                           tr_code, rq_name, i, "일자").strip()
            close = self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)",
                                            tr_code, rq_name, i, "현재가").strip()
            self.data.append([date, close])


    def get_current_price(self, code):
        """ 현재 주가 가져오기 """
        self.kiwoom.dynamicCall("SetInputValue(QString, QString)", "종목코드", code)
        self.kiwoom.dynamicCall("CommRqData(QString, QString, int, QString)", 
                                "현재가조회", "opt10001", 0, "0101")

        loop = QEventLoop()
        handler = lambda *args: (self.on_receive_price_data(*args), loop.quit())
        self.kiwoom.OnReceiveTrData.connect(handler)
        loop.exec_()
        self.kiwoom.OnReceiveTrData.disconnect(handler)
        return self.current_price

    def on_receive_price_data(self, scr_no, rq_name, tr_code, record_name, prev_next):
        self.current_price = int(
            self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", 
                                    tr_code, rq_name, 0, "현재가").strip()
        )

    def get_stock_data(self, code):
        """ 📊 종목의 5일선 & 20일선 데이터 가져오기 """
        self.kiwoom.dynamicCall("SetInputValue(QString, QString)", "종목코드", code)
        self.kiwoom.dynamicCall("CommRqData(QString, QString, int, QString)", 
                                "주식일봉차트조회", "opt10081", 0, "0101")

        loop = QEventLoop()
        handler = lambda *args: (self.on_receive_stock_data(*args), loop.quit())
        self.kiwoom.OnReceiveTrData.connect(handler)
        self.data = []
        loop.exec_()
        self.kiwoom.OnReceiveTrData.disconnect(handler)

        df = pd.DataFrame(self.data, columns=['date', 'close'])
        df['close'] = df['close'].astype(int)
        df['5MA'] = df['close'].rolling(window=5).mean()
        df['20MA'] = df['close'].rolling(window=20).mean()
        return df

    def on_receive_stock_data(self, scr_no, rq_name, tr_code, record_name, prev_next):
        count = self.kiwoom.dynamicCall("GetRepeatCnt(QString, QString)", tr_code, rq_name)
        for i in range(count):
            date = self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", 
                                           tr_code, rq_name, i, "일자").strip()
            close = self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", 
                                            tr_code, rq_name, i, "현재가").strip()
            self.data.append([date, close])

    def check_exit_conditions(self, code, entry_price):
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
        df = self.get_stock_data(code)
        if len(df) < 20:
            return False

        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]

        if prev_row['5MA'] < prev_row['20MA'] and last_row['5MA'] > last_row['20MA']:
            print(f"🚀 {code} 골든크로스 발생! 매수 실행")
            self.send_order(code, 1)
            return True
        return False

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
                        entry_prices.pop(code, None)
                        print(f"📢 {code} 매도 완료, 관리 목록에서 제거")

            time.sleep(60)

    def send_order(self, code, order_type):
        print(f"주문 전송: {code}, 주문타입: {order_type}")

if __name__ == "__main__":
    trader = KiwoomTrader()
    stock_list = trader.get_filtered_stocks()
    trader.run_backtest(stock_list, start_date_for_data="20250101", 
                          start_date_for_backtest="20250201", end_date="20250225")
