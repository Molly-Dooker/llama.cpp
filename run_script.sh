#!/bin/bash

# --- 기본 설정 ---
# REPOPATH와 MODELPATH는 환경변수로 설정되어 있다고 가정합니다.
# 필요시 아래 주석을 해제하고 경로를 설정하세요.
# export REPOPATH='/home/user/Repo/llama.cpp' # 예시 경로
# export MODELPATH='/home/user/Repo/llama.cpp/model.gguf' # 예시 모델 경로

# --- 명령어 정의 ---
CMD1="$REPOPATH/build/bin/llama-server -m $MODELPATH"
PYTHON_EXEC_CMD2="~/.venv/llama.cpp/bin/python" # CMD2 및 오토 테스트에 사용될 Python
APP_PY_SCRIPT="$REPOPATH/_webdemo/app.py"
CMD2="$PYTHON_EXEC_CMD2 $APP_PY_SCRIPT"

# --- 오토 테스트 설정 ---
STRESS_TEST_SCRIPT_NAME="_auto_test_app.py" # 오토 테스트 Python 스크립트 파일명
# 스크립트의 실제 위치에 따라 경로를 조정하세요.
# 현재 디렉토리에 있다고 가정. 만약 다른 곳에 있다면 절대 경로로 지정하는 것이 좋음.
STRESS_TEST_SCRIPT_PATH="./$STRESS_TEST_SCRIPT_NAME"
# STRESS_TEST_SCRIPT_PATH="$REPOPATH/tests/$STRESS_TEST_SCRIPT_NAME" # 예시: repo 내 다른 경로

STRESS_TEST_CMD_BASE="$PYTHON_EXEC_CMD2 $STRESS_TEST_SCRIPT_PATH" # 기본 명령어 템플릿

# --- 로그 파일 설정 ---
SERVER_LOG_FILE="/dev/null" # 서버 명령어들의 로그 (숨김)
STRESS_TEST_LOG_FILE="stress_test_output.log" # 오토 테스트 로그
STRESS_PID_FILE="stress_test.pid" # 오토 테스트 PID 저장 파일

# --- 함수 정의 ---

# 백그라운드에서 서버 및 웹앱 실행
run_commands() {
    echo "백그라운드에서 다음 명령어들을 실행합니다 (로그 숨김):"
    # REPOPATH, MODELPATH 확인
    if [ -z "$REPOPATH" ] || [ ! -d "$REPOPATH" ]; then
        echo "오류: REPOPATH ('$REPOPATH')가 설정되지 않았거나 유효한 디렉토리가 아닙니다."
        return 1
    fi
    if [ -z "$MODELPATH" ] || [ ! -f "$MODELPATH" ]; then
        echo "오류: MODELPATH ('$MODELPATH')가 설정되지 않았거나 유효한 파일이 아닙니다."
        return 1
    fi

    echo "1. $CMD1"
    nohup sh -c "$CMD1" > "$SERVER_LOG_FILE" 2>&1 &
    local cmd1_pid=$!
    if ps -p $cmd1_pid > /dev/null; then
        echo "  명령어 1이 백그라운드에서 실행되었습니다. (PID: $cmd1_pid)"
    else
        echo "  명령어 1 실행에 실패했거나 즉시 종료되었습니다."
    fi

    echo "2. $CMD2"
    expanded_cmd2=$(eval echo "$CMD2") # ~ 확장
    nohup sh -c "$expanded_cmd2" > "$SERVER_LOG_FILE" 2>&1 &
    local cmd2_pid=$!
    if ps -p $cmd2_pid > /dev/null; then
        echo "  명령어 2가 백그라운드에서 실행되었습니다. (PID: $cmd2_pid)"
    else
        echo "  명령어 2 실행에 실패했거나 즉시 종료되었습니다."
    fi
    echo "PID는 'pgrep -f \"부분_명령어\"' 등으로 확인할 수 있습니다."
}

# 특정 포트 사용 프로세스 중지
stop_processes_on_port() {
    local port=$1
    echo "포트 $port 에서 LISTEN 중인 TCP 프로세스를 찾아 종료합니다..."
    # lsof 대신 ss 사용 (더 현대적이고 가벼울 수 있음, lsof도 유효)
    # pids_output=$(lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null)
    pids_output=$(ss -ltnp "sport = :$port" 2>/dev/null | grep LISTEN | awk '{print $NF}' | sed -E 's/.*pid=([0-9]+).*/\1/')


    if [ -n "$pids_output" ]; then
        echo "$pids_output" | while IFS= read -r pid; do
            if [ -n "$pid" ] && [ "$pid" -gt 0 ]; then # 유효한 PID인지 확인
                echo "  PID $pid (포트 $port 사용) 프로세스를 강제 종료합니다 (kill -9 $pid)."
                if kill -9 "$pid" 2>/dev/null; then
                    echo "    PID $pid 종료 성공."
                else
                    echo "    PID $pid 종료 실패 (이미 종료되었거나 권한 문제일 수 있습니다)."
                fi
            fi
        done
    else
        echo "  포트 $port 에서 LISTEN 중인 TCP 프로세스를 찾을 수 없습니다."
    fi
}

# 서버 및 웹앱 중지
stop_all_commands() {
    echo "llama-server 관련 프로세스 종료 시도 (pgrep -af \"llama-server -m\")..."
    # CMD1에 정의된 llama-server 명령어와 최대한 유사하게 pkill -f 패턴 사용
    # 모델 경로에 공백 등이 있을 수 있으므로 따옴표 처리 고려 (여기서는 변수 그대로 사용)
    pkill -f "$CMD1"
    # 좀 더 관대한 패턴
    pkill -f "llama-server -m"
    if [ $? -eq 0 ]; then # pkill은 하나라도 죽이면 0 반환
        echo "  llama-server 관련 프로세스에 종료 신호를 보냈습니다."
    else
        echo "  실행 중인 llama-server 프로세스를 찾지 못했거나 종료에 실패했을 수 있습니다."
    fi

    # WebDemo (CMD2)는 5000 포트를 사용한다고 가정 (Python 스크립트에서 BASE_URL 포트)
    stop_processes_on_port 5000
    # llama-server가 사용하는 기본 API 포트 (보통 8080)
    stop_processes_on_port 8080

    echo "지정된 포트 및 이름 기반의 프로세스들에 대한 중지 작업이 완료되었습니다."
}

# 오토 테스트 실행
run_stress_test_command() {
    local expanded_python_exec
    expanded_python_exec=$(eval echo "$PYTHON_EXEC_CMD2") # ~ 확장

    local script_abs_path
    # STRESS_TEST_SCRIPT_PATH를 절대 경로로 변환
    if [[ "$STRESS_TEST_SCRIPT_PATH" == /* ]]; then
        script_abs_path="$STRESS_TEST_SCRIPT_PATH"
    else
        script_abs_path="$(pwd)/$STRESS_TEST_SCRIPT_PATH"
    fi

    if [ ! -f "$script_abs_path" ]; then
        echo "오류: 오토 테스트 스크립트 '$script_abs_path'를 찾을 수 없습니다."
        return 1
    fi

    local actual_stress_cmd="$expanded_python_exec $script_abs_path"

    echo "백그라운드에서 오토 테스트를 실행합니다 (로그: $STRESS_TEST_LOG_FILE):"
    echo "실행 명령어: $actual_stress_cmd"

    # nohup으로 실행하고 PID를 파일에 저장
    nohup $actual_stress_cmd > "$STRESS_TEST_LOG_FILE" 2>&1 &
    local stress_pid=$!

    # PID가 유효한지 잠깐 확인
    sleep 0.5
    if ps -p $stress_pid > /dev/null; then
        echo "$stress_pid" > "$STRESS_PID_FILE" # PID 파일에 저장
        echo "  오토 테스트가 백그라운드에서 실행되었습니다. (PID: $stress_pid)"
        echo "  PID가 '$STRESS_PID_FILE' 파일에 저장되었습니다."
        echo "  로그는 '$STRESS_TEST_LOG_FILE' 파일에서 확인할 수 있습니다."
        echo "  테스트를 중지하려면 'stress_stop' 메뉴를 사용하세요."
    else
        echo "  오토 테스트 실행에 실패했거나 즉시 종료되었습니다."
        echo "  로그 파일 '$STRESS_TEST_LOG_FILE'을 확인해주세요."
        # 실패 시 PID 파일 삭제
        if [ -f "$STRESS_PID_FILE" ]; then
            rm "$STRESS_PID_FILE"
        fi
    fi
}

# 오토 테스트 중지
stop_stress_test_command() {
    echo "오토 테스트 Python 스크립트 프로세스를 찾아 종료합니다..."

    if [ -f "$STRESS_PID_FILE" ]; then
        local pid_to_kill
        pid_to_kill=$(cat "$STRESS_PID_FILE")
        if [ -n "$pid_to_kill" ] && ps -p "$pid_to_kill" > /dev/null; then
            echo "  PID 파일 ($STRESS_PID_FILE)에서 찾은 PID $pid_to_kill 프로세스를 종료 시도합니다."
            if kill "$pid_to_kill" 2>/dev/null; then # SIGTERM 전송
                echo "    PID $pid_to_kill 에 종료 신호(SIGTERM)를 보냈습니다. 잠시 대기합니다..."
                sleep 3 # Python 스크립트가 정상 종료할 시간
                if ps -p "$pid_to_kill" > /dev/null; then
                    echo "    PID $pid_to_kill 프로세스가 아직 실행 중입니다. 강제 종료(SIGKILL)합니다."
                    if kill -9 "$pid_to_kill" 2>/dev/null; then
                        echo "      PID $pid_to_kill 강제 종료 성공."
                    else
                        echo "      PID $pid_to_kill 강제 종료 실패."
                    fi
                else
                    echo "    PID $pid_to_kill 성공적으로 종료되었습니다."
                fi
            else
                echo "    PID $pid_to_kill 에 종료 신호 전송 실패 (이미 종료되었거나 권한 문제)."
            fi
            rm "$STRESS_PID_FILE" # PID 파일 삭제
        else
            echo "  PID 파일 ($STRESS_PID_FILE)에 있는 PID $pid_to_kill 가 현재 실행 중이지 않거나 유효하지 않습니다."
            rm "$STRESS_PID_FILE" # 유효하지 않은 PID 파일 삭제
        fi
    else
        echo "  PID 파일 ($STRESS_PID_FILE)을 찾을 수 없습니다. 명령줄 기반으로 검색합니다."
        # PID 파일이 없을 경우, pgrep으로 시도 (정확도가 낮을 수 있음)
        local expanded_python_exec
        expanded_python_exec=$(eval echo "$PYTHON_EXEC_CMD2")
        local script_abs_path
        if [[ "$STRESS_TEST_SCRIPT_PATH" == /* ]]; then
            script_abs_path="$STRESS_TEST_SCRIPT_PATH"
        else
            script_abs_path="$(pwd)/$STRESS_TEST_SCRIPT_PATH" # 또는 그냥 STRESS_TEST_SCRIPT_NAME 으로 검색
        fi

        # pgrep 검색 패턴: "python_실행파일_경로 스크립트_절대경로"
        # 또는 "python_실행파일_경로 .*스크립트이름"
        local search_pattern_precise="$expanded_python_exec $script_abs_path"
        local search_pattern_generic="$expanded_python_exec.*$STRESS_TEST_SCRIPT_NAME"

        echo "  pgrep 시도 패턴 1 (정확): \"$search_pattern_precise\""
        pids_found=$(pgrep -f "$search_pattern_precise")

        if [ -z "$pids_found" ]; then
            echo "  패턴 1로 찾지 못함. pgrep 시도 패턴 2 (일반): \"$search_pattern_generic\""
            pids_found=$(pgrep -f "$search_pattern_generic")
        fi

        if [ -n "$pids_found" ]; then
            echo "  pgrep으로 다음 PID(들)을 찾았습니다: $pids_found"
            echo "$pids_found" | while IFS= read -r pid; do
                if [ -n "$pid" ]; then
                    echo "    PID $pid 종료 시도..."
                    if kill "$pid" 2>/dev/null; then # SIGTERM
                        echo "      PID $pid 에 SIGTERM 전송됨. 3초 대기..."
                        sleep 3
                        if ps -p "$pid" > /dev/null; then
                            echo "      PID $pid 아직 실행 중. SIGKILL 전송..."
                            kill -9 "$pid" 2>/dev/null && echo "        SIGKILL 성공." || echo "        SIGKILL 실패."
                        else
                            echo "      PID $pid 종료됨."
                        fi
                    else
                        echo "      PID $pid 에 SIGTERM 전송 실패 (이미 없음?)."
                    fi
                fi
            done
        else
            echo "  실행 중인 오토 테스트 스크립트 ('$STRESS_TEST_SCRIPT_NAME' 관련)를 pgrep으로도 찾을 수 없습니다."
            echo "  팁: 'ps aux | grep -E \"python.*$STRESS_TEST_SCRIPT_NAME\"'으로 직접 확인해보세요."
        fi
    fi
}


# 메뉴 표시
show_menu() {
    echo ""
    echo "스크립트 작업을 선택하세요:"
    echo "  run           - 데모 실행"
    echo "  stop          - 데모 중지"
    echo "  auto_run      - 오토 스크립트 실행"
    echo "  auto_stop     - 오토 스크립트 중지"
    echo "  exit          - 스크립트 종료"
    echo -n "선택: "
}

# --- 메인 루프 ---
while true; do
    show_menu
    read -r choice

    case "$choice" in
        run)
            # 환경 변수 확인은 run_commands 내부로 이동
            run_commands
            ;;
        stop)
            if ! command -v ss &> /dev/null && ! command -v lsof &> /dev/null ; then
                echo "경고: 'ss' 또는 'lsof' 명령어를 찾을 수 없습니다. 포트 기반 종료가 제한될 수 있습니다."
            fi
            if ! command -v pkill &> /dev/null ; then
                echo "경고: 'pkill' 명령어를 찾을 수 없습니다. 이름 기반 종료가 제한될 수 있습니다."
            fi
            stop_all_commands
            ;;
        auto_run)
            expanded_python_exec=$(eval echo "$PYTHON_EXEC_CMD2")
            if ! command -v "$expanded_python_exec" &> /dev/null && [[ ! -f "$expanded_python_exec" ]]; then
                 echo "오류: Python 실행 파일 '$expanded_python_exec'를 찾을 수 없습니다."
                 echo "      Python 가상환경 경로를 확인하거나 시스템 Python을 사용하도록 PYTHON_EXEC_CMD2를 수정하세요."
            else
                run_stress_test_command
            fi
            ;;
        auto_stop)
             if ! command -v pgrep &> /dev/null || ! command -v kill &> /dev/null; then
                echo "오류: 'pgrep' 또는 'kill' 명령어를 찾을 수 없습니다. 'stress_stop' 기능을 사용하려면 설치해야 합니다."
            else
                stop_stress_test_command
            fi
            ;;
        logs)
            if [ -f "$STRESS_TEST_LOG_FILE" ]; then
                echo "오토 테스트 로그 실시간 보기 (Ctrl+C로 중단):"
                tail -f "$STRESS_TEST_LOG_FILE"
            else
                echo "오토 테스트 로그 파일 '$STRESS_TEST_LOG_FILE'이(가) 아직 생성되지 않았습니다."
            fi
            ;;
        exit)
            echo "스크립트를 종료합니다."
            # 스크립트 종료 시 임시 PID 파일 정리
            if [ -f "$STRESS_PID_FILE" ]; then
                rm "$STRESS_PID_FILE"
            fi
            exit 0
            ;;
        *)
            echo "잘못된 선택입니다. 메뉴에서 골라 입력하세요."
            ;;
    esac
done