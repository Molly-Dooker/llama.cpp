from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import time
import random

# --- 테스트 설정 ---
BASE_URL = "http://localhost:5000"  # chat.html이 제공되는 URL
CHAT_INPUT_SELECTOR = "textarea#prompt" # CSS 선택자 사용
CHAT_BOX_SELECTOR = "div#chat"          # CSS 선택자 사용
ASSISTANT_BUBBLE_SELECTOR = f"{CHAT_BOX_SELECTOR} > div.assistant" # 어시스턴트 말풍선 선택자

# NUMBER_OF_MESSAGES 변수 제거
MAX_RESPONSE_WAIT_TIME = 60  # 각 응답 완료를 기다릴 최대 시간 (초)
MESSAGE_INTERVAL_SECONDS = 1.5 # 메시지 전송 간 간격 (초)

# 스트리밍 완료 감지 설정
STREAMING_CHECK_INTERVAL = 0.5  # 내용 변경 감지 주기 (초)
STREAMING_STABLE_CHECKS = 4     # 이 횟수만큼 내용 변경 없으면 완료로 간주

TEST_PROMPTS = [
    "2 더하기 2는 얼마인가요?",
    "화씨 100도는 섭씨로 몇 도인가요?",
    "3의 팩토리얼 값은 얼마인가요?",
    "태양계에서 가장 큰 행성은 무엇인가요?",
    "지구의 둘레는 약 얼마인가요?",
    "HTML에서 H1 태그는 어떤 역할을 하나요?",
    "인공지능이란 무엇인가요?",
    "세계에서 가장 긴 강은 무엇인가요?",
    "삼각형의 내각의 합은 얼마인가요?",
    "영어로 '사랑'은 어떻게 표현하나요?",
    "음악 장르 중 재즈에 대해 간단히 설명해주세요.",
    "프로그래밍이란 무엇인가요?",
    "기술의 발전이 앞으로 우리 삶에 미칠 영향은 무엇인가요?",
    "LLM에 대해 간단히 설명해주시겠어요?",
    "파이썬으로 'Hello, World!'를 출력하는 코드를 보여주세요.",
    "가장 높은 산의 이름과 높이를 알려주세요.",
    "인공지능의 미래에 대해 어떻게 생각하세요?",
    "가장 최근에 학습한 내용은 무엇인가요?",
    "복잡한 수학 문제를 풀어줄 수 있나요? 예를 들어, 12345 * 67890 = ?",
    "Neural Processing Unit 에 대해 간단히 설명해주시겠어요?",
]

def initialize_driver():
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless')
    # options.add_argument('--disable-gpu')
    # options.add_argument('--window-size=1920x1080')
    try:
        driver = webdriver.Chrome(options=options)
        print("WebDriver 초기화 성공.")
        return driver
    except Exception as e:
        print(f"WebDriver 초기화 실패: {e}")
        print("ChromeDriver가 설치되어 있고 PATH에 설정되어 있는지 확인하세요.")
        return None

def wait_for_streaming_completion(driver, num_bubbles_before, timeout_seconds):
    overall_start_time = time.time()
    try:
        WebDriverWait(driver, 15).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, ASSISTANT_BUBBLE_SELECTOR)) > num_bubbles_before and \
                      "⏳ 생각 중..." not in d.find_elements(By.CSS_SELECTOR, ASSISTANT_BUBBLE_SELECTOR)[-1].text and \
                      d.find_elements(By.CSS_SELECTOR, ASSISTANT_BUBBLE_SELECTOR)[-1].text.strip() != ""
        )
        print("초기 응답 수신됨. 전체 스트리밍 완료 대기 중...")
    except TimeoutException:
        print("오류: 초기 응답을 시간 내에 받지 못했습니다 (15초 초과).")
        raise

    last_raw_text = None
    stable_checks_count = 0
    
    while True:
        if time.time() - overall_start_time > timeout_seconds:
            raise TimeoutException(f"스트리밍 응답이 {timeout_seconds}초 내에 완료(안정화)되지 않았습니다.")
        try:
            assistant_bubbles = driver.find_elements(By.CSS_SELECTOR, ASSISTANT_BUBBLE_SELECTOR)
            if not assistant_bubbles or len(assistant_bubbles) <= num_bubbles_before:
                time.sleep(STREAMING_CHECK_INTERVAL)
                continue
            last_bubble = assistant_bubbles[-1]
            current_raw_text = last_bubble.get_attribute('data-raw-full-text')
            if current_raw_text is not None and current_raw_text == last_raw_text:
                stable_checks_count += 1
            else:
                stable_checks_count = 0
                last_raw_text = current_raw_text
            if stable_checks_count >= STREAMING_STABLE_CHECKS and last_raw_text is not None and last_raw_text.strip() != "":
                print(f"스트리밍 완료 감지됨 (내용 {STREAMING_STABLE_CHECKS * STREAMING_CHECK_INTERVAL:.1f}초 동안 안정).")
                return
        except StaleElementReferenceException:
            print("Debug: StaleElementReferenceException 발생, 요소 다시 찾기 시도 중...")
            stable_checks_count = 0
            last_raw_text = None
            time.sleep(STREAMING_CHECK_INTERVAL * 2)
            continue
        except Exception as e_loop:
            print(f"Debug: 스트리밍 대기 중 예외 발생: {type(e_loop).__name__} - {e_loop}")
            time.sleep(STREAMING_CHECK_INTERVAL)
            continue
        time.sleep(STREAMING_CHECK_INTERVAL)

def run_stress_test(driver):
    print(f"웹 페이지 로딩: {BASE_URL}")
    try:
        driver.get(BASE_URL)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, CHAT_INPUT_SELECTOR))
        )
        print("웹 페이지 로드 완료. 무한 스트레스 테스트를 시작합니다 (종료하려면 Ctrl+C).")
    except TimeoutException:
        print(f"오류: 웹 페이지 로드 시간 초과 ({BASE_URL}). 서버가 실행 중인지 확인하세요.")
        return
    except Exception as e:
        print(f"오류: 웹 페이지 로드 중 예외 발생 - {e}")
        return

    successful_sends = 0
    failed_sends = 0
    response_times = []
    message_count = 0 # 메시지 카운터 초기화

    try: # KeyboardInterrupt를 감지하기 위한 try 블록
        while True: # 무한 루프
            message_count += 1
            current_prompt = random.choice(TEST_PROMPTS)
            print(f"\n--- 메시지 {message_count} 전송 시도 ---")
            print(f"프롬프트: {current_prompt}")

            try:
                chat_input_element = driver.find_element(By.CSS_SELECTOR, CHAT_INPUT_SELECTOR)
                num_assistant_bubbles_before = len(driver.find_elements(By.CSS_SELECTOR, ASSISTANT_BUBBLE_SELECTOR))

                chat_input_element.clear()
                chat_input_element.send_keys(current_prompt)
                time.sleep(0.1)
                chat_input_element.send_keys(Keys.ENTER)

                start_time = time.time()
                print("메시지 전송 완료. 응답 스트리밍 완료 대기 중...")

                wait_for_streaming_completion(driver, num_assistant_bubbles_before, MAX_RESPONSE_WAIT_TIME)
                
                end_time = time.time()
                response_time = end_time - start_time
                response_times.append(response_time)
                print(f"응답 수신 및 스트리밍 완료. (총 응답 시간: {response_time:.2f}초)")

                last_assistant_response_element = driver.find_elements(By.CSS_SELECTOR, ASSISTANT_BUBBLE_SELECTOR)[-1]
                response_text_for_log = last_assistant_response_element.get_attribute('data-raw-full-text') or last_assistant_response_element.text
                print(f"응답 내용 (일부): {response_text_for_log[:100].strip()}...")
                successful_sends += 1

            except TimeoutException as e_timeout:
                print(f"오류: {e_timeout}")
                failed_sends += 1
                driver.save_screenshot(f"timeout_error_{message_count}.png")
                print(f"스크린샷 'timeout_error_{message_count}.png' 저장됨.")
            except NoSuchElementException as e_no_such:
                print(f"오류: 웹 요소를 찾을 수 없습니다 - {e_no_such}.")
                failed_sends += 1
                driver.save_screenshot(f"nosuchelement_error_{message_count}.png")
                print(f"스크린샷 'nosuchelement_error_{message_count}.png' 저장됨.")
                print("심각한 오류로 인해 테스트 루프를 중단합니다. (페이지 구조 변경 가능성)")
                break # 무한 루프 중단
            except Exception as e_general:
                print(f"오류: 메시지 처리 중 예외 발생 - {type(e_general).__name__}: {e_general}")
                failed_sends += 1
                driver.save_screenshot(f"general_error_{message_count}.png")
                print(f"스크린샷 'general_error_{message_count}.png' 저장됨.")
            
            print(f"{MESSAGE_INTERVAL_SECONDS}초 대기...")
            time.sleep(MESSAGE_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\n사용자에 의해 테스트가 중단되었습니다.")
    finally: # 루프가 정상적으로 끝나거나(여기서는 KeyboardInterrupt로만 끝남) 예외로 끝날 때 항상 실행
        print("\n--- 스트레스 테스트 결과 (중단 시점) ---")
        print(f"총 시도한 메시지 수: {message_count}")
        print(f"성공적으로 전송 및 응답 받은 메시지 수: {successful_sends}")
        print(f"실패한 메시지 수: {failed_sends}")
        if response_times:
            avg_response_time = sum(response_times) / len(response_times) if response_times else 0
            min_response_time = min(response_times) if response_times else 0
            max_response_time = max(response_times) if response_times else 0
            print(f"평균 응답 시간: {avg_response_time:.2f}초")
            print(f"최소 응답 시간: {min_response_time:.2f}초")
            print(f"최대 응답 시간: {max_response_time:.2f}초")
        else:
            print("처리된 응답이 없어 응답 시간 통계를 계산할 수 없습니다.")

if __name__ == "__main__":
    web_driver = None
    try:
        print("테스트를 시작하기 전에 다음을 확인해주세요:")
        print("1. `./run.sh run` (또는 해당 스크립트)을 통해 llama-server와 Flask 앱(app.py)이 실행 중이어야 합니다.")
        print(f"2. Flask 앱이 {BASE_URL} 에서 정상적으로 서비스 중이어야 합니다.")
        # input("계속하려면 Enter 키를 누르세요...")

        web_driver = initialize_driver()
        if web_driver:
            run_stress_test(web_driver) # 이 함수는 KeyboardInterrupt를 내부적으로 처리하고 통계를 출력

    except KeyboardInterrupt: # 만약 initialize_driver 등 외부에서 Ctrl+C가 눌린 경우
        print("\n스크립트 실행 중 사용자에 의해 중단됨 (초기화 단계).")
    except Exception as e: # 기타 예외
        print(f"스크립트 실행 중 예상치 못한 최상위 오류 발생: {e}")
    finally:
        if web_driver:
            print("WebDriver 종료 중...")
            web_driver.quit()
            print("WebDriver 종료 완료.")