from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import random

# --- 테스트 설정 ---
BASE_URL = "http://localhost:5000"  # chat.html이 제공되는 URL
CHAT_INPUT_SELECTOR = "textarea#prompt" # CSS 선택자 사용
SEND_BUTTON_SELECTOR = "button#sendBtn" # CSS 선택자 사용
CHAT_BOX_SELECTOR = "div#chat"          # CSS 선택자 사용
ASSISTANT_BUBBLE_SELECTOR = f"{CHAT_BOX_SELECTOR} > div.assistant"

NUMBER_OF_MESSAGES = 50  # 보낼 총 메시지 수
MAX_WAIT_FOR_RESPONSE = 45 # 각 응답을 기다릴 최대 시간 (초)
MESSAGE_INTERVAL_SECONDS = 1.5 # 메시지 전송 간 간격 (초)

# 테스트에 사용할 프롬프트 목록 (다양하게 추가 가능)
TEST_PROMPTS = [
    "안녕하세요, 오늘 기분은 어떠신가요?",
    "대한민국의 현재 대통령은 누구인가요?",
    "LLM에 대해 간단히 설명해주시겠어요?",
    "파이썬으로 'Hello, World!'를 출력하는 코드를 보여주세요.",
    "가장 좋아하는 책은 무엇인가요?",
    "오늘의 주요 뉴스는 무엇인가요?",
    "간단한 농담 하나 해주세요.",
    "내일 서울 날씨는 어떨 것으로 예상되나요?",
    "가장 높은 산의 이름과 높이를 알려주세요.",
    "인공지능의 미래에 대해 어떻게 생각하세요?",
    "짧은 시 한 편 지어줄 수 있나요?",
    "현재 시간을 알려주세요.",
    "이 대화의 목적은 무엇인가요?",
    "가장 최근에 학습한 내용은 무엇인가요?",
    "복잡한 수학 문제를 풀어줄 수 있나요? 예를 들어, 12345 * 67890 = ?",
    "Neural Processing Unit 에 대해 설명해줘",
    "짧은 재밌는 이야기 하나 해줘"
]

def initialize_driver():
    """웹 드라이버를 초기화합니다."""
    # Chrome 옵션 설정 (필요에 따라 headless 모드 등 추가 가능)
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless')  # 브라우저 UI 없이 실행
    # options.add_argument('--disable-gpu') # headless 모드 시 권장
    # options.add_argument('--window-size=1920x1080') # headless 모드 시 창 크기 지정
    try:
        driver = webdriver.Chrome(options=options)
        print("WebDriver 초기화 성공.")
        return driver
    except Exception as e:
        print(f"WebDriver 초기화 실패: {e}")
        print("ChromeDriver가 설치되어 있고 PATH에 설정되어 있는지 확인하세요.")
        return None

def run_stress_test(driver):
    """스트레스 테스트를 실행합니다."""
    print(f"웹 페이지 로딩: {BASE_URL}")
    try:
        driver.get(BASE_URL)
        # 채팅 입력창이 나타날 때까지 대기
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, CHAT_INPUT_SELECTOR))
        )
        print("웹 페이지 로드 완료.")
    except TimeoutException:
        print(f"오류: 웹 페이지 로드 시간 초과 ({BASE_URL}). 서버가 실행 중인지 확인하세요.")
        return
    except Exception as e:
        print(f"오류: 웹 페이지 로드 중 예외 발생 - {e}")
        return

    successful_sends = 0
    failed_sends = 0
    response_times = []

    for i in range(NUMBER_OF_MESSAGES):
        current_prompt = random.choice(TEST_PROMPTS)
        print(f"\n--- 메시지 {i + 1}/{NUMBER_OF_MESSAGES} 전송 시도 ---")
        print(f"프롬프트: {current_prompt}")

        try:
            chat_input_element = driver.find_element(By.CSS_SELECTOR, CHAT_INPUT_SELECTOR)
            # send_button_element = driver.find_element(By.CSS_SELECTOR, SEND_BUTTON_SELECTOR) # Enter로 전송하므로 버튼 클릭은 불필요

            # 이전 어시스턴트 메시지 개수 확인
            num_assistant_bubbles_before = len(driver.find_elements(By.CSS_SELECTOR, ASSISTANT_BUBBLE_SELECTOR))

            chat_input_element.clear()
            chat_input_element.send_keys(current_prompt)
            time.sleep(0.1) # 입력 후 잠시 대기
            chat_input_element.send_keys(Keys.ENTER) # Enter 키로 메시지 전송

            start_time = time.time()
            print("메시지 전송 완료. 응답 대기 중...")

            # 새 어시스턴트 메시지가 나타나고, "생각 중" 상태가 아닐 때까지 대기
            WebDriverWait(driver, MAX_WAIT_FOR_RESPONSE).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, ASSISTANT_BUBBLE_SELECTOR)) > num_assistant_bubbles_before and \
                          "⏳ 생각 중..." not in d.find_elements(By.CSS_SELECTOR, ASSISTANT_BUBBLE_SELECTOR)[-1].text and \
                          d.find_elements(By.CSS_SELECTOR, ASSISTANT_BUBBLE_SELECTOR)[-1].text.strip() != ""
            )

            end_time = time.time()
            response_time = end_time - start_time
            response_times.append(response_time)
            print(f"응답 수신 완료. (응답 시간: {response_time:.2f}초)")

            # 마지막 어시스턴트 응답 내용 (간략히)
            last_assistant_response_element = driver.find_elements(By.CSS_SELECTOR, ASSISTANT_BUBBLE_SELECTOR)[-1]
            response_text = last_assistant_response_element.text
            print(f"응답 내용 (일부): {response_text[:100].strip()}...")

            successful_sends += 1

        except TimeoutException:
            print(f"오류: 응답 시간 초과 ({MAX_WAIT_FOR_RESPONSE}초). 서버가 응답하지 않거나 응답이 너무 깁니다.")
            failed_sends += 1
            driver.save_screenshot(f"timeout_error_{i+1}.png") # 타임아웃 시 스크린샷 저장
            print(f"스크린샷 'timeout_error_{i+1}.png' 저장됨.")
        except NoSuchElementException as e:
            print(f"오류: 웹 요소를 찾을 수 없습니다 - {e}. 페이지 구조가 변경되었을 수 있습니다.")
            failed_sends += 1
            driver.save_screenshot(f"nosuchelement_error_{i+1}.png")
            print(f"스크린샷 'nosuchelement_error_{i+1}.png' 저장됨.")
            break # 심각한 오류 시 중단
        except Exception as e:
            print(f"오류: 메시지 전송/응답 처리 중 예외 발생 - {type(e).__name__}: {e}")
            failed_sends += 1
            driver.save_screenshot(f"general_error_{i+1}.png")
            print(f"스크린샷 'general_error_{i+1}.png' 저장됨.")

        # 다음 메시지 전송 전 잠시 대기
        if i < NUMBER_OF_MESSAGES - 1:
            print(f"{MESSAGE_INTERVAL_SECONDS}초 대기...")
            time.sleep(MESSAGE_INTERVAL_SECONDS)

    print("\n--- 스트레스 테스트 결과 ---")
    print(f"총 시도한 메시지 수: {NUMBER_OF_MESSAGES}")
    print(f"성공적으로 전송 및 응답 받은 메시지 수: {successful_sends}")
    print(f"실패한 메시지 수: {failed_sends}")
    if response_times:
        print(f"평균 응답 시간: {sum(response_times) / len(response_times):.2f}초")
        print(f"최소 응답 시간: {min(response_times):.2f}초")
        print(f"최대 응답 시간: {max(response_times):.2f}초")

if __name__ == "__main__":
    web_driver = None
    try:
        # 1. 백엔드 서버 및 llama-server 실행 확인
        print("테스트를 시작하기 전에 다음을 확인해주세요:")
        print("1. `./run.sh run` (또는 해당 스크립트)을 통해 llama-server와 Flask 앱(app.py)이 실행 중이어야 합니다.")
        print(f"2. Flask 앱이 {BASE_URL} 에서 정상적으로 서비스 중이어야 합니다.")
        # input("계속하려면 Enter 키를 누르세요...") # 사용자 확인 대기

        web_driver = initialize_driver()
        if web_driver:
            run_stress_test(web_driver)
    except KeyboardInterrupt:
        print("\n사용자에 의해 테스트가 중단되었습니다.")
    except Exception as e:
        print(f"스크립트 실행 중 예상치 못한 오류 발생: {e}")
    finally:
        if web_driver:
            print("WebDriver 종료 중...")
            web_driver.quit()
            print("WebDriver 종료 완료.")