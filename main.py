from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, Update
import chess
import random
from sqlalchemy import create_engine, Column, Integer, String, select
from sqlalchemy.orm import DeclarativeBase, sessionmaker
import json

BOT_TOKEN = ""


class Base(DeclarativeBase):
    pass

engine = create_engine('sqlite:///user_progress.db', echo=False)
Session = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String, nullable=True)
    solved_count = Column(Integer, default=0)
    total_rating = Column(Integer, default=0)
    current_level = Column(String, default="Средняя")

Base.metadata.create_all(engine)

# клавиатурка
reply_keyboard = [
    ["/start", "/help", "/game", "/stats", "/reset"]
]
markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)

active_games = {}

# грузим задачке
try:
    with open('puzzles_data.json', 'r', encoding='utf-8') as f:
        puzzles_data = json.load(f)
    
    puzzles = []
    for puzzle in puzzles_data:
        rating = puzzle.get("Rating", 1500)
        
        if rating < 2600:
            level = "Средняя"
        elif rating < 3000:
            level = "Сложная"
        else:
            level = "Очень сложная"
        
        moves = puzzle["Moves"].split() if "Moves" in puzzle else []
        
        themes = puzzle.get("Themes", "").split()
        condition = ""
        
        if "mate" in themes or "mateIn2" in themes or "mateIn3" in themes:
            total_moves = len(moves)
            if total_moves == 1:
                condition = "Мат в 1 ход"
            elif total_moves == 2:
                condition = "Мат в 2 хода"
            elif total_moves == 3:
                condition = "Мат в 3 хода"
            else:
                condition = f"Мат в {total_moves // 2 + 1} ходов"
        else:
            if "advancedPawn" in themes or "promotion" in themes:
                condition = "Продвините пешку"
            elif "endgame" in themes:
                condition = "Эндшпиль"
            elif "crushing" in themes:
                condition = "Решающая атака"
            elif "attraction" in themes:
                condition = "Привлечение фигуры"
            else:
                condition = "Выиграйте материал"
        
        puzzles.append({
            "fen": puzzle["FEN"],
            "solution": moves,
            "level": level,
            "condition": condition,
            "rating": rating,
            "themes": themes
        })
    
    print(f"Загружено {len(puzzles)} задач")
    
except FileNotFoundError:
    print("Ошибка: файл puzzles_data.json не найден.")
    puzzles = []
except json.JSONDecodeError:
    print("Ошибка: неверный формат JSON в puzzles_data.json")
    puzzles = []
except KeyError as e:
    print(f"Ошибка: отсутствует ключ {e} в puzzles_data.json")
    puzzles = []


def ascii_board(fen: str) -> str:
    board = chess.Board(fen)
    if board.turn == chess.BLACK:
        return str(board)[::-1]
    return str(board)

def print_debug_info(task):
    print("\n" + "="*50)
    print("ИНФОРМАЦИЯ О ЗАДАЧЕ:")
    print(f"FEN: {task['fen']}")
    print(f"Уровень: {task['level']} (рейтинг: {task.get('rating', 'N/A')})")
    print(f"Условие: {task['condition']}")
    print(f"Решение: {task['solution']}")
    
    board = chess.Board(task['fen'])
    print("\nДоска с координатами:")
    print(board.unicode(borders=True, empty_square='.'))
    
    test_board = chess.Board(task['fen'])
    move_number = 1
    
    for i, move_uci in enumerate(task['solution']):
        try:
            move = chess.Move.from_uci(move_uci)
            player = "Белые" if test_board.turn == chess.WHITE else "Чёрные"
            
            if move in test_board.legal_moves:
                test_board.push(move)
                print(f"{move_number}. {player}: {move_uci}")
                
                if test_board.is_checkmate():
                    print("   -> МАТ")
                elif test_board.is_check():
                    print("   -> ШАХ")
                
                if i % 2 == 1:
                    move_number += 1
            else:
                print(f"ОШИБКА: Ход {move_uci} невозможен!")
                break
                
        except Exception as e:
            print(f"ОШИБКА в ходе {move_uci}: {e}")
    
    print("="*50 + "\n")

# команди 
async def start(update, context):
    user_id = update.effective_user.id
    username = update.effective_user.username

    session = Session()
    user = session.scalar(select(User).where(User.telegram_id == user_id))
    if not user:
        user = User(telegram_id=user_id, username=username)
        session.add(user)
        session.commit()
        text = (
            "Добро пожаловать в шахматный тренажёр!\n"
            "Вы зарегистрированы.\n"
            "Используйте /game для начала задачи."
        )
    else:
        text = f"Ты уже зарегистрирован!\nРешено задач: {user.solved_count}"
    session.close()

    await update.message.reply_text(text, reply_markup=markup)

async def help_command(update, context):
    text = (
        "Шахматный бот-тренажёр\n\n"
        "Команды:\n"
        "/start - регистрация\n"
        "/game - начать задачу\n"
        "/stats - статистика\n"
        "/help - справка\n\n"
        "Формат хода:\n"
        "e2 e4  (ход с e2 на e4)\n"
        "O-O    (короткая рокировка)\n"
        "O-O-O  (длинная рокировка)"
    )
    await update.message.reply_text(text, reply_markup=markup)

async def stats(update, context):
    user_id = update.effective_user.id
    session = Session()
    user = session.scalar(select(User).where(User.telegram_id == user_id))
    session.close()

    if not user:
        await update.message.reply_text("Сначала зарегистрируйтесь: /start")
        return

    avg_rating = user.total_rating // user.solved_count if user.solved_count > 0 else 0
    
    text = (
        f"Ваша статистика:\n"
        f"Решено задач: {user.solved_count}\n"
        f"Текущий уровень: {user.current_level}\n"
    )
    await update.message.reply_text(text, reply_markup=markup)

async def game(update, context):
    buttons = [
        [InlineKeyboardButton("Средняя (<2600)", callback_data="level_Средняя")],
        [InlineKeyboardButton("Сложная (2600-3000)", callback_data="level_Сложная")],
        [InlineKeyboardButton("Очень сложная (>3000)", callback_data="level_Очень сложная")],
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Выберите уровень сложности задачи:", reply_markup=keyboard)

async def level_choice(update, context):
    query = update.callback_query
    await query.answer()

    level = query.data.replace("level_", "")
    
    level_tasks = [task for task in puzzles if task.get('level') == level]
    
    if not level_tasks:
        await query.edit_message_text(f"Для уровня '{level}' задач пока нет.")
        return

    task = random.choice(level_tasks)

    user_id = query.from_user.id
    board = chess.Board(task["fen"])
    active_games[user_id] = {
        "board": board,
        "solution": task["solution"].copy(),
        "level": level,
        "condition": task["condition"],
        "rating": task.get("rating", 1500),
        "current_move": 0,
        "history": [],
        "show_board": False
    }

    session = Session()
    user = session.scalar(select(User).where(User.telegram_id == user_id))
    if user:
        user.current_level = level
        session.commit()
    session.close()

    total_moves = len(task["solution"])
    color = "белые" if board.turn == chess.WHITE else "чёрные"
    
    moves_needed = (total_moves + 1) // 2
    if "Мат в" in task["condition"]:
        moves_text = task["condition"]
    elif moves_needed == 1:
        moves_text = "1 ход"
    else:
        moves_text = f"{moves_needed} ходов"
    
    rating_text = f"\nРейтинг задачи: {task.get('rating', 'N/A')}" if task.get('rating') else ""
    
    text = (
        f"Уровень: {level}\n"
        f"Условие: {task['condition']}\n"
        f"Ходят: {color}\n"
        f"Всего ходов в решении: {total_moves} ({moves_text})"
        f"{rating_text}\n\n"
        "Доска скрыта. Нажмите 'Показать доску', чтобы увидеть позицию.\n\n"
        "Введите ваш ход:"
    )
    
    buttons = [
        [InlineKeyboardButton("Показать доску", callback_data="show_board")],
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(text, reply_markup=keyboard)
    
    print_debug_info(task)

async def reset_game(update, context):
    """Обработчик кнопки сброса задачи - вызывает команду reset"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    username = query.from_user.username or "игрок"

    if user_id in active_games:
        del active_games[user_id]

    session = Session()
    user = session.scalar(select(User).where(User.telegram_id == user_id))
    session.close()

    solved = user.solved_count if user else 0

    text = (
        f"Задача сброшена (считается нерешённой).\n\n"
        f"Решено задач: {solved}\n"
        f"Выберите действие:"
    )

    await query.edit_message_text(text, reply_markup=markup)

async def show_board(update, context):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id not in active_games:
        return
    
    task_data = active_games[user_id]
    task_data["show_board"] = True
    
    board = task_data["board"]
    board_ascii = ascii_board(board.fen())
    
    current_text = query.message.text
    lines = current_text.split('\n')
    
    header_lines = []
    for line in lines:
        if "Доска скрыта" not in line:
            header_lines.append(line)
        else:
            break
    
    header_text = '\n'.join(header_lines[:6])
    
    text = f"{header_text}\n\n{board_ascii}\n\nВведите ваш ход:"
    
    buttons = [
        [InlineKeyboardButton("Скрыть доску", callback_data="hide_board")],
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(text, reply_markup=keyboard)

async def hide_board(update, context):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id not in active_games:
        return
    
    task_data = active_games[user_id]
    task_data["show_board"] = False
    
    current_text = query.message.text
    lines = current_text.split('\n')
    
    header_lines = []
    board_started = False
    for line in lines:
        if any(piece in line for piece in ['K', 'Q', 'R', 'B', 'N', 'P', '.', ' ']) and len(line.strip()) > 0:
            board_started = True
            continue
        if not board_started:
            header_lines.append(line)
    
    header_text = '\n'.join(header_lines[:6])
    
    text = f"{header_text}\n\nДоска скрыта. Нажмите 'Показать доску', чтобы увидеть позицию.\n\nВведите ваш ход:"
    
    buttons = [
        [InlineKeyboardButton("Показать доску", callback_data="show_board")],
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(text, reply_markup=keyboard)

# ходы
def check_solution(board, move, task_data):
    solution = task_data["solution"]
    current_move = task_data["current_move"]
    condition = task_data["condition"]
    history = task_data["history"]
    
    if current_move >= len(solution):
        return True, "Задача уже решена!", True
    
    expected_move = solution[current_move]
    
    if move.uci() != expected_move:
        correct_move = chess.Move.from_uci(expected_move)
        if move == correct_move:
            pass
        else:
            return False, f"Неправильный ход", False

    board.push(move)
    history.append(move.uci())
    current_move += 1
    task_data["current_move"] = current_move
    

    if current_move == len(solution) -1:
        return True, "Задача решена правильно!", True

    if current_move < len(solution):
        opponent_move_uci = solution[current_move]
        opponent_move = chess.Move.from_uci(opponent_move_uci)
        
        if opponent_move in board.legal_moves:
            board.push(opponent_move)
            history.append(opponent_move_uci)
            current_move += 1
            task_data["current_move"] = current_move
            
            opponent_color = "чёрные" if board.turn == chess.WHITE else "белые"
            
            remaining_moves = (len(solution) - current_move + 1) // 2
            move_number = (current_move // 2) + 1
            
            message = f"Правильно!\n{opponent_color} сходили: {opponent_move_uci}\n"
            
            if remaining_moves > 0:
                message += f"Ход {move_number}. Осталось: {remaining_moves} ход(ов)\n"
            
            player_color = "белые" if board.turn == chess.WHITE else "чёрные"
            message += f"\nВаш ход ({player_color}):"
            
            return True, message, False
        else:
            #ход противника невозможен
            for _ in range(2):
                if history:
                    board.pop()
                    history.pop()
            task_data["current_move"] = 0
            task_data["history"] = []
            return False, f"Ошибка в задаче: ход противника {opponent_move_uci} невозможен", False
    
    return False, "Ошибка в логике проверки", False

async def text_handler(update, context):
    user_id = update.effective_user.id
    if user_id not in active_games:
        await update.message.reply_text("Сначала выберите задачу: /game", reply_markup=markup)
        return

    raw_text = update.message.text.strip()
    text = raw_text.upper()

    if not all(c.isascii() for c in raw_text):
        await update.message.reply_text("Используйте английскую раскладку клавиатуры.", reply_markup=markup)
        return

    board = active_games[user_id]["board"]
    task_data = active_games[user_id]

    move_uci = None
    
    if text == "O-O":
        if board.turn == chess.WHITE:
            move_uci = "e1g1" if chess.Move.from_uci("e1g1") in board.legal_moves else None
        else:
            move_uci = "e8g8" if chess.Move.from_uci("e8g8") in board.legal_moves else None
            
    elif text == "O-O-O":
        if board.turn == chess.WHITE:
            move_uci = "e1c1" if chess.Move.from_uci("e1c1") in board.legal_moves else None
        else:
            move_uci = "e8c8" if chess.Move.from_uci("e8c8") in board.legal_moves else None
            
    elif " " in text:
        try:
            a, b = text.split()
            move_uci = a.lower() + b.lower()
        except:
            pass
    elif len(text) == 4 and text.isalpha():
        move_uci = text.lower()
    elif len(text) == 5 and text[4] in "nbrq":
        move_uci = text.lower()

    if not move_uci:
        await update.message.reply_text(
            "Неверный формат хода. Используйте:\n"
            "e2 e4\n"
            "e2e4\n"
            "O-O\n"
            "O-O-O\n"
            "e7e8q",
            reply_markup=markup
        )
        return

    try:
        move = chess.Move.from_uci(move_uci)
    except ValueError:
        await update.message.reply_text("Некорректный ход. (возможно вы ввели некорректные координаты)", reply_markup=markup)
        return

    if move not in board.legal_moves:
        await update.message.reply_text("Этот ход невозможен по правилам шахмат.", reply_markup=markup)
        return

    is_correct, message, solved = check_solution(board, move, task_data)
    
    if is_correct and solved:
        #задача решена
        await update.message.reply_text(message, reply_markup=markup)
        
        #обновляем
        session = Session()
        user = session.scalar(select(User).where(User.telegram_id == user_id))
        if user:
            user.solved_count += 1
            user.total_rating += task_data.get("rating", 1000)
            session.commit()
        session.close()
        
        del active_games[user_id]
        
    elif is_correct and not solved:
        # верный ход
        await update.message.reply_text(message, reply_markup=markup)
        
    else:
        # неверно
        await update.message.reply_text(message, reply_markup=markup)

async def text_handler(update, context):
    user_id = update.effective_user.id
    if user_id not in active_games:
        await update.message.reply_text("Сначала выберите задачу: /game", reply_markup=markup)
        return

    raw_text = update.message.text.strip()
    text = raw_text.upper()

    if not all(c.isascii() for c in raw_text):
        await update.message.reply_text("Используйте английскую раскладку клавиатуры.", reply_markup=markup)
        return

    board = active_games[user_id]["board"]
    task_data = active_games[user_id]

    move_uci = None
    
    if text == "O-O":
        if board.turn == chess.WHITE:
            move_uci = "e1g1" if chess.Move.from_uci("e1g1") in board.legal_moves else None
        else:
            move_uci = "e8g8" if chess.Move.from_uci("e8g8") in board.legal_moves else None
            
    elif text == "O-O-O":
        if board.turn == chess.WHITE:
            move_uci = "e1c1" if chess.Move.from_uci("e1c1") in board.legal_moves else None
        else:
            move_uci = "e8c8" if chess.Move.from_uci("e8c8") in board.legal_moves else None
            
    elif " " in text:
        try:
            a, b = text.split()
            move_uci = a.lower() + b.lower()
        except:
            pass
    elif len(text) == 4 and text.isalpha():
        move_uci = text.lower()
    elif len(text) == 5 and text[4] in "nbrq":
        move_uci = text.lower()

    if not move_uci:
        await update.message.reply_text(
            "Неверный формат хода. Используйте:\n"
            "e2 e4\n"
            "e2e4\n"
            "O-O\n"
            "O-O-O\n"
            "e7e8q",
            reply_markup=markup
        )
        return

    try:
        move = chess.Move.from_uci(move_uci)
    except ValueError:
        await update.message.reply_text("Некорректные координаты.", reply_markup=markup)
        return

    if move not in board.legal_moves:
        await update.message.reply_text("Этот ход невозможен по правилам шахмат.", reply_markup=markup)
        return

    is_correct, message, solved = check_solution(board, move, task_data)
    
    if is_correct and solved:
        await update.message.reply_text(message, reply_markup=markup)
        
        session = Session()
        user = session.scalar(select(User).where(User.telegram_id == user_id))
        if user:
            user.solved_count += 1
            user.total_rating += task_data.get("rating", 1000)
            session.commit()
        session.close()
        
        del active_games[user_id]
        
    elif is_correct and not solved:
        await update.message.reply_text(message, reply_markup=markup)
        
    else:
        await update.message.reply_text(message, reply_markup=markup)

async def reset(update, context):
    user_id = update.effective_user.id
    username = update.effective_user.username or "игрок"

    if user_id in active_games:
        del active_games[user_id]

    session = Session()
    user = session.scalar(select(User).where(User.telegram_id == user_id))
    session.close()

    solved = user.solved_count if user else 0

    text = (
        f"Задача сброшена (считается нерешённой).\n\n"
        f"Решено задач: {solved}\n"
        f"Выберите действие:"
    )

    await update.message.reply_text(text, reply_markup=markup)

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("game", game))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CallbackQueryHandler(level_choice, pattern="^level_"))
    app.add_handler(CallbackQueryHandler(reset_game, pattern="^reset_game$"))
    app.add_handler(CallbackQueryHandler(show_board, pattern="^show_board$"))
    app.add_handler(CallbackQueryHandler(hide_board, pattern="^hide_board$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("Бот запущен.")
    app.run_polling()

if __name__ == "__main__":
    main()