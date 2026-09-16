import pygame
import math
import random

# ============================================================
# ИНИЦИАЛИЗАЦИЯ И АДАПТАЦИЯ К ЭКРАНУ
# ============================================================
pygame.init()

info = pygame.display.Info()
SW = info.current_w
SH = info.current_h

screen = pygame.display.set_mode((SW, SH), pygame.FULLSCREEN)
pygame.display.set_caption("Экосистема (пошаговая)")
clock = pygame.time.Clock()

# Размер ячейки: адаптивный, но не меньше 3 пикселей
SCALE = max(3, min(SW, SH) // 64)
W = SW // SCALE   # ширина сетки в ячейках
H = SH // SCALE   # высота сетки в ячейках
TOTAL = W * H

# Корректируем размер окна под целое число ячеек
SW = W * SCALE
SH = H * SCALE
screen = pygame.display.set_mode((SW, SH), pygame.FULLSCREEN)

font_size = max(18, SH // 35)
font = pygame.font.SysFont(None, font_size)

# ============================================================
# СЕТКИ МИРА
# ============================================================
water = [0.0] * TOTAL   # уровень воды в ячейке
plant = [0.0] * TOTAL   # уровень растения в ячейке

# Сетка занятости ячеек животными:
# 0 = свободно, 1 = травоядное, 2 = хищник
occupancy = [0] * TOTAL

# ---------- Травоядные ----------
# Предел популяции пропорционален размеру карты, чтобы на маленьких
# сетках хищники успевали регулировать травоядных, а на больших не
# было искусственного дефицита места.
MAX_H = max(100, min(int(TOTAL * 0.04), 1200))
hgx = [0] * MAX_H   # координата X в ячейках (целая)
hgy = [0] * MAX_H   # координата Y в ячейках (целая)
hbe = [0.0] * MAX_H # энергия
count_h = 0

# ---------- Хищники ----------
MAX_P = max(5, min(int(TOTAL * 0.0015), 30))
pgx = [0] * MAX_P
pgy = [0] * MAX_P
pbe = [0.0] * MAX_P
count_p = 0

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================
def idx(x, y):
    """Индекс ячейки в массиве"""
    return y * W + x

def in_bounds(x, y):
    """Проверка: ячейка внутри границ"""
    return 0 <= x < W and 0 <= y < H

def draw_cell(gx, gy, color):
    """Рисует одну ячейку сетки (занимает весь блок SCALE × SCALE)"""
    pygame.draw.rect(screen, color, 
                    (gx * SCALE, gy * SCALE, SCALE, SCALE))

def draw_text(text, x, y, color):
    """Рисует текст в экранных координатах"""
    img = font.render(text, True, color)
    screen.blit(img, (x, y))

# ============================================================
# ИНИЦИАЛИЗАЦИЯ МИРА
# ============================================================
# Стартовая вода и растения
for i in range(TOTAL):
    if random.randint(0, 99) < 12:
        water[i] = 45 + random.randint(0, 45)
    if water[i] > 25:
        if random.randint(0, 99) < 65:
            plant[i] = 25 + random.randint(0, 40)

# ---------- Постоянные источники воды (родники) ----------
# Без них вся вода на карте испаряется за пару минут и экосистема
# необратимо вымирает, если игрок не поливает её вручную. Родники —
# часть изначально влажных ячеек — медленно подтягивают уровень воды
# к SPRING_LEVEL, создавая долгоживущие оазисы, вокруг которых
# держится растительность.
springs = [i for i in range(TOTAL) if water[i] > 60 and random.random() < 0.25]
SPRING_LEVEL = 70.0

# ---------- Стартовое население по коэффициентам ----------
count_h = int(TOTAL * 0.010)
count_h = max(12, min(count_h, MAX_H))

count_p = int(TOTAL * 0.0012)
count_p = max(3, min(count_p, MAX_P))

# Размещаем травоядных по свободным ячейкам
placed = 0
attempts = 0
while placed < count_h and attempts < TOTAL * 5:
    gx = random.randint(0, W - 1)
    gy = random.randint(0, H - 1)
    i = idx(gx, gy)
    if occupancy[i] == 0:
        hgx[placed] = gx
        hgy[placed] = gy
        hbe[placed] = 80.0
        occupancy[i] = 1
        placed += 1
    attempts += 1
count_h = placed

# Размещаем хищников по свободным ячейкам
placed = 0
attempts = 0
while placed < count_p and attempts < TOTAL * 5:
    gx = random.randint(0, W - 1)
    gy = random.randint(0, H - 1)
    i = idx(gx, gy)
    if occupancy[i] == 0:
        pgx[placed] = gx
        pgy[placed] = gy
        pbe[placed] = 70.0
        occupancy[i] = 2
        placed += 1
    attempts += 1
count_p = placed

# ---------- Цикл дня и ночи ----------
CYCLE_LEN = 600   # 600 тактов = 20 секунд при 30 FPS (ускорено для наглядности)
t = 0

h_max_seen = count_h
p_max_seen = count_p
water_cells = 0

# Возможные направления движения (8 соседних ячеек + оставаться на месте)
DIRS = [
    (-1, -1), (0, -1), (1, -1),
    (-1,  0),          (1,  0),
    (-1,  1), (0,  1), (1,  1),
    (0, 0)  # остаться на месте
]
MOVE_DIRS = DIRS[:-1]  # без "остаться на месте" — для поиска направления

# ---------- Погода и параметры баланса ----------
active_rains = []          # активные дождевые тучи: [cx, cy, radius, ticks_left]
RAIN_CHANCE = 0.006        # шанс появления новой тучи за такт
EVAP_RATE = 0.006          # испарение — доля от текущего запаса воды за такт
PLANT_WATER_COST = 0.10    # расход воды растением при росте

FLEE_RADIUS = 3            # радиус, в котором травоядное замечает хищника
FLEE_CHANCE = 0.5          # шанс, что травоядное предпочтёт бегство поиску еды
CATCH_CHANCE = 0.30        # шанс хищника поймать травоядное в соседней ячейке
DECOMP_PLANT = 8.0         # питательные вещества, возвращаемые почве при гибели от голода
IMMIGRATION_CHANCE = 0.02  # шанс пополнения популяции извне при её почти полном исчезновении


def apply_moves(count, gx, gy, be, moves, species_id, max_count):
    """
    Применяет решения о движении и размножении без потери животных.
    Раньше, если и целевая, и исходная ячейка оказывались заняты
    (конфликт при одновременном движении нескольких особей), животное
    молча выпадало из симуляции без всякой причины (не голод, не хищник).
    Теперь для него ищется любая свободная соседняя ячейка, и только
    если карта вокруг полностью забита, особь остаётся на месте.
    moves[i] = (new_gx, new_gy, e, new_born_или_None)
    """
    for i in range(count):
        occupancy[idx(gx[i], gy[i])] = 0

    order = list(range(count))
    random.shuffle(order)  # порядок обработки не должен давать преимущества по индексу

    out_gx = [0] * max_count
    out_gy = [0] * max_count
    out_be = [0.0] * max_count
    new_count = 0
    births = []

    for i in order:
        new_gx, new_gy, e, new_born = moves[i]
        if e <= 0:
            continue  # умерло от голода — ячейка уже освобождена выше

        old_gx, old_gy = gx[i], gy[i]
        target_i = idx(new_gx, new_gy)
        if occupancy[target_i] == 0:
            occupancy[target_i] = species_id
            out_gx[new_count] = new_gx; out_gy[new_count] = new_gy; out_be[new_count] = e
            new_count += 1
        else:
            old_i = idx(old_gx, old_gy)
            if occupancy[old_i] == 0:
                occupancy[old_i] = species_id
                out_gx[new_count] = old_gx; out_gy[new_count] = old_gy; out_be[new_count] = e
                new_count += 1
            else:
                placed = False
                for dx, dy in DIRS:
                    nx, ny = old_gx + dx, old_gy + dy
                    if in_bounds(nx, ny) and occupancy[idx(nx, ny)] == 0:
                        occupancy[idx(nx, ny)] = species_id
                        out_gx[new_count] = nx; out_gy[new_count] = ny; out_be[new_count] = e
                        new_count += 1
                        placed = True
                        break
                if not placed:
                    # окружено со всех сторон — остаёмся на месте, но не исчезаем
                    out_gx[new_count] = old_gx; out_gy[new_count] = old_gy; out_be[new_count] = e
                    new_count += 1

        if new_born and new_count < max_count:
            births.append(new_born)

    for bx, by, bbe in births:
        if new_count >= max_count:
            break
        bi = idx(bx, by)
        if occupancy[bi] == 0:
            occupancy[bi] = species_id
            out_gx[new_count] = bx; out_gy[new_count] = by; out_be[new_count] = bbe
            new_count += 1

    for i in range(new_count):
        gx[i] = out_gx[i]; gy[i] = out_gy[i]; be[i] = out_be[i]

    return new_count

# ============================================================
# ГЛАВНЫЙ ЦИКЛ ПОШАГОВОЙ СИМУЛЯЦИИ
# ============================================================
running = True
while running:
    # ---------- ОБРАБОТКА СОБЫТИЙ ----------
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE or event.key == pygame.K_AC_BACK:
                running = False

    # Дождь: полив при касании
    mouse_pressed = pygame.mouse.get_pressed()
    if mouse_pressed[0]:
        mx, my = pygame.mouse.get_pos()
        gx = mx // SCALE
        gy = my // SCALE
        r = max(3, SCALE // 2)
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy <= r * r:
                    nx, ny = gx + dx, gy + dy
                    if in_bounds(nx, ny):
                        water[idx(nx, ny)] = 100.0

    # ========================================================
    # НАЧАЛО ТАКТА СИМУЛЯЦИИ
    # ========================================================
    t += 1
    cyc = (t % CYCLE_LEN) / CYCLE_LEN

    # Освещённость
    light = 1.0
    if cyc < 0.20:
        light = cyc / 0.20
    elif cyc > 0.80:
        light = (1.0 - cyc) / 0.20
    if light < 0.25:
        light = 0.25

    # ---------- ПОГОДА: родники и дождь ----------
    # Родники медленно подтягивают уровень воды к SPRING_LEVEL — это
    # единственный надёжный источник воды, не зависящий от игрока.
    for si in springs:
        if water[si] < SPRING_LEVEL:
            water[si] = min(SPRING_LEVEL, water[si] + 1.0)

    # Изредка по карте проходят дождевые тучи, подпитывая всё вокруг
    if random.random() < RAIN_CHANCE:
        cx = random.randint(0, W - 1)
        cy = random.randint(0, H - 1)
        radius = random.randint(max(3, W // 12), max(5, W // 7))
        duration = random.randint(40, 100)
        active_rains.append([cx, cy, radius, duration])

    still_raining = []
    for rain in active_rains:
        rcx, rcy, rradius, rdur = rain
        for dy in range(-rradius, rradius + 1):
            for dx in range(-rradius, rradius + 1):
                if dx * dx + dy * dy <= rradius * rradius:
                    nx, ny = rcx + dx, rcy + dy
                    if in_bounds(nx, ny):
                        ni = idx(nx, ny)
                        if water[ni] < 90:
                            water[ni] += 0.5
        rdur -= 1
        if rdur > 0:
            still_raining.append([rcx, rcy, rradius, rdur])
    active_rains = still_raining

    # ---------- ФИЗИКА ВОДЫ ----------
    water_cells = 0
    for y in range(H):
        for x in range(W):
            i = idx(x, y)
            w = water[i]
            
            if w > 0:
                water_cells += 1

            # Диффузия для внутренних ячеек
            if 0 < x < W - 1 and 0 < y < H - 1:
                if w > 2:
                    avg = (water[i-1] + water[i+1] + water[i-W] + water[i+W]) / 4.0
                    if w > avg:
                        flow = (w - avg) * 0.20
                        water[i]   = w - flow * 4
                        water[i-1] += flow
                        water[i+1] += flow
                        water[i-W] += flow
                        water[i+W] += flow
            else:
                # Просачивание из границ
                if w > 5:
                    if x == 0 and water[i+1] < w:
                        water[i+1] += 1; water[i] -= 1
                    if x == W-1 and water[i-1] < w:
                        water[i-1] += 1; water[i] -= 1
                    if y == 0 and water[i+W] < w:
                        water[i+W] += 1; water[i] -= 1
                    if y == H-1 and water[i-W] < w:
                        water[i-W] += 1; water[i] -= 1

            # Испарение — доля от текущего запаса, а не фиксированная
            # величина: раньше вода терялась с фиксированной скоростью
            # независимо от объёма, и весь мир высыхал дотла за пару
            # минут без дождя игрока
            if water[i] > 0:
                water[i] -= water[i] * EVAP_RATE
                if water[i] < 0.05:
                    water[i] = 0

    # ---------- РОСТ РАСТЕНИЙ ----------
    for y in range(H):
        for x in range(W):
            i = idx(x, y)
            w = water[i]
            p = plant[i]

            if light > 0.5:
                if w > 1 and p < 100 and occupancy[i] == 0:
                    plant[i] = p + 0.35
                    water[i] = w - PLANT_WATER_COST
                    if water[i] < 0:
                        water[i] = 0
            else:
                if p > 0:
                    plant[i] = p - 0.04
                    if plant[i] < 0:
                        plant[i] = 0

    # ---------- ШАГ ТРАВОЯДНЫХ ----------
    h_drain = 0.6      # расход энергии за такт (было 0.05*30=1.5, снижен)
    if light < 0.5:
        h_drain = 1.0  # ночью больше

    # Сначала собираем все решения о движении, потом применяем
    # чтобы не было конфликтов из-за порядка обработки
    h_moves = [None] * count_h  # (new_gx, new_gy, ate_amount)

    for hi in range(count_h):
        gx = hgx[hi]
        gy = hgy[hi]
        e = hbe[hi]
        i_cur = idx(gx, gy)

        # 1. Сначала едим растение в текущей ячейке (откушенная порция
        # уменьшена, иначе выедание намного обгоняет рост растений и
        # травоядные регулярно выжирают карту подчистую)
        ate = 0.0
        if plant[i_cur] > 3:
            eaten = min(3.0, plant[i_cur])
            plant[i_cur] -= eaten
            ate = eaten * 0.85

        # 2. Выбираем направление для движения.
        # Если рядом замечен хищник — с некоторой вероятностью бежим от
        # него, иначе ищем соседнюю ячейку с растением (едой). Раньше
        # травоядные вообще не реагировали на хищников, из-за чего
        # хищник при равной скорости почти гарантированно ловил жертву
        # при прямом преследовании.
        nearest_p_dist = FLEE_RADIUS * FLEE_RADIUS + 1
        nearest_p = -1
        for pi_scan in range(count_p):
            ddx = pgx[pi_scan] - gx
            ddy = pgy[pi_scan] - gy
            dd = ddx * ddx + ddy * ddy
            if dd < nearest_p_dist:
                nearest_p_dist = dd
                nearest_p = pi_scan

        best_dir = None
        if nearest_p >= 0 and random.random() < FLEE_CHANCE:
            px, py = pgx[nearest_p], pgy[nearest_p]
            best_away = -1
            for dx, dy in MOVE_DIRS:
                nx, ny = gx + dx, gy + dy
                if in_bounds(nx, ny) and occupancy[idx(nx, ny)] == 0:
                    away = (nx - px) * (nx - px) + (ny - py) * (ny - py)
                    if away > best_away:
                        best_away = away
                        best_dir = (dx, dy)
        else:
            best_plant = -1

            # Перемешиваем направления для случайности
            shuffled_dirs = MOVE_DIRS[:]
            random.shuffle(shuffled_dirs)

            for dx, dy in shuffled_dirs:
                nx, ny = gx + dx, gy + dy
                if in_bounds(nx, ny):
                    ni = idx(nx, ny)
                    if occupancy[ni] == 0:  # ячейка свободна
                        if plant[ni] > best_plant:
                            best_plant = plant[ni]
                            best_dir = (dx, dy)

            # Если нет еды рядом — выбираем случайное свободное направление
            if best_dir is None or best_plant < 2:
                candidates = []
                for dx, dy in shuffled_dirs:
                    nx, ny = gx + dx, gy + dy
                    if in_bounds(nx, ny) and occupancy[idx(nx, ny)] == 0:
                        candidates.append((dx, dy))
                if candidates:
                    best_dir = random.choice(candidates)

        # 3. Обновляем энергию
        e = e + ate - h_drain

        # 4. Размножение (порог поднят, иначе рост популяции
        # многократно обгоняет скорость восстановления растений, и
        # травоядные регулярно съедают всю карту подчистую, а затем
        # массово гибнут от голода)
        new_born = None
        if e > 160 and count_h < MAX_H:
            # Ищем свободную соседнюю ячейку для потомка
            free_neighbor = None
            for dx, dy in MOVE_DIRS:
                nx, ny = gx + dx, gy + dy
                if in_bounds(nx, ny) and occupancy[idx(nx, ny)] == 0:
                    free_neighbor = (nx, ny)
                    break
            if free_neighbor:
                new_born = (free_neighbor[0], free_neighbor[1], e / 2)
                e = e / 2

        # 5. Запоминаем решение
        if best_dir:
            new_gx = gx + best_dir[0]
            new_gy = gy + best_dir[1]
        else:
            new_gx = gx
            new_gy = gy

        h_moves[hi] = (new_gx, new_gy, e, new_born)

    # Погибшие от голода возвращают часть биомассы почве (перегной),
    # иначе трупы просто исчезают без следа — замкнутый цикл питательных
    # веществ отсутствовал
    for hi in range(count_h):
        if h_moves[hi][2] <= 0:
            ci = idx(hgx[hi], hgy[hi])
            plant[ci] = min(100.0, plant[ci] + DECOMP_PLANT)

    # Применяем движения травоядных (конфликтующие особи больше не
    # исчезают молча — см. apply_moves)
    count_h = apply_moves(count_h, hgx, hgy, hbe, h_moves, 1, MAX_H)

    # Подсадка небольшой группы травоядных извне, если популяция почти
    # полностью вымерла — без этого один неудачный период засухи или
    # перевыпаса необратимо обнулял всю карту до конца симуляции
    if count_h < 3 and random.random() < IMMIGRATION_CHANCE:
        for _ in range(3):
            if count_h >= MAX_H:
                break
            gx_im = random.randint(0, W - 1)
            gy_im = random.randint(0, H - 1)
            i_im = idx(gx_im, gy_im)
            if occupancy[i_im] == 0:
                occupancy[i_im] = 1
                hgx[count_h] = gx_im
                hgy[count_h] = gy_im
                hbe[count_h] = 80.0
                count_h += 1

    # ---------- ШАГ ХИЩНИКОВ ----------
    # Расход и стартовая энергия снижены, а поимка жертвы больше не
    # гарантирована и не даёт колоссальный разовый прирост энергии —
    # раньше один-единственный контакт с жертвой почти всегда сразу
    # выводил хищника на порог размножения, и популяция хищников
    # взрывообразно росла до предела и выедала всех травоядных подчистую.
    p_drain = 0.5
    if light < 0.5:
        p_drain = 0.8

    p_moves = [None] * count_p
    hunt_radius = max(10, min(W, H) // 10)  # радиус поиска жертвы

    for pi in range(count_p):
        gx = pgx[pi]
        gy = pgy[pi]
        e = pbe[pi]

        # 1. Ищем ближайшую жертву в радиусе
        best_h = -1
        best_dist = hunt_radius * hunt_radius + 1

        for hi in range(count_h):
            dx = hgx[hi] - gx
            dy = hgy[hi] - gy
            dist_sq = dx * dx + dy * dy
            if dist_sq < best_dist:
                best_dist = dist_sq
                best_h = hi

        # 2. Выбираем направление
        ate = 0.0
        if best_h >= 0:
            # Есть жертва — движемся к ней
            hx = hgx[best_h]
            hy = hgy[best_h]

            # Если жертва в соседней ячейке — есть шанс поймать её
            if abs(hx - gx) <= 1 and abs(hy - gy) <= 1 and (hx != gx or hy != gy):
                if random.random() < CATCH_CHANCE:
                    hbe[best_h] = -1  # помечаем травоядного как съеденного
                    ate = 15.0

            # Выбираем направление к жертве
            step_x = 0
            step_y = 0
            if hx > gx:
                step_x = 1
            elif hx < gx:
                step_x = -1
            if hy > gy:
                step_y = 1
            elif hy < gy:
                step_y = -1

            # Проверяем целевая ячейка свободна?
            nx, ny = gx + step_x, gy + step_y
            if in_bounds(nx, ny) and occupancy[idx(nx, ny)] == 0:
                best_dir = (step_x, step_y)
            else:
                # Пробуем только по X или только по Y
                if step_x != 0 and in_bounds(gx + step_x, gy) and occupancy[idx(gx + step_x, gy)] == 0:
                    best_dir = (step_x, 0)
                elif step_y != 0 and in_bounds(gx, gy + step_y) and occupancy[idx(gx, gy + step_y)] == 0:
                    best_dir = (0, step_y)
                else:
                    best_dir = (0, 0)  # стоим на месте
        else:
            # Нет жертвы — случайное блуждание
            candidates = [(0, 0)]
            for dx, dy in MOVE_DIRS:
                nx, ny = gx + dx, gy + dy
                if in_bounds(nx, ny) and occupancy[idx(nx, ny)] == 0:
                    candidates.append((dx, dy))
            best_dir = random.choice(candidates)

        # 3. Обновляем энергию
        e = e + ate - p_drain
        if e > 110:
            e = 110

        # 4. Размножение — только если хищник только что поел. Раньше
        # порог зависел лишь от накопленной энергии, и хищники продолжали
        # плодиться даже тогда, когда жертв на карте почти не осталось,
        # что довершало истребление травоядных и затем губило самих
        # хищников. Теперь темп размножения естественно падает вместе
        # с частотой удачной охоты.
        new_born = None
        if ate > 0 and e > 85 and count_p < MAX_P:
            free_neighbor = None
            for dx, dy in MOVE_DIRS:
                nx, ny = gx + dx, gy + dy
                if in_bounds(nx, ny) and occupancy[idx(nx, ny)] == 0:
                    free_neighbor = (nx, ny)
                    break
            if free_neighbor:
                new_born = (free_neighbor[0], free_neighbor[1], e / 2)
                e = e / 2

        # 5. Запоминаем решение
        if best_dir:
            new_gx = gx + best_dir[0]
            new_gy = gy + best_dir[1]
        else:
            new_gx = gx
            new_gy = gy

        p_moves[pi] = (new_gx, new_gy, e, new_born)

    # Сначала удаляем съеденных травоядных и освобождаем их ячейки
    # (их биомассу уже "унёс" поймавший хищник, поэтому, в отличие от
    # смерти от голода, здесь почва ничего не получает)
    new_h_count2 = 0
    for hi in range(count_h):
        if hbe[hi] > 0:
            hgx[new_h_count2] = hgx[hi]
            hgy[new_h_count2] = hgy[hi]
            hbe[new_h_count2] = hbe[hi]
            new_h_count2 += 1
        else:
            occupancy[idx(hgx[hi], hgy[hi])] = 0
    count_h = new_h_count2

    # Применяем движения хищников (конфликтующие особи больше не
    # исчезают молча — см. apply_moves)
    count_p = apply_moves(count_p, pgx, pgy, pbe, p_moves, 2, MAX_P)

    # Подсадка одного хищника извне, если хищники почти вымерли, а
    # травоядных на карте достаточно — без этого случайная затяжная
    # неудачная охота необратимо обнуляла вид хищников до конца
    # симуляции (что и наблюдалось в тестах баланса)
    if count_p < 2 and count_h > 5 and random.random() < IMMIGRATION_CHANCE:
        gx_im = random.randint(0, W - 1)
        gy_im = random.randint(0, H - 1)
        i_im = idx(gx_im, gy_im)
        if occupancy[i_im] == 0:
            occupancy[i_im] = 2
            pgx[count_p] = gx_im
            pgy[count_p] = gy_im
            pbe[count_p] = 70.0
            count_p += 1

    # ---------- Статистика ----------
    if count_h > h_max_seen:
        h_max_seen = count_h
    if count_p > p_max_seen:
        p_max_seen = count_p

    # ========================================================
    # ОТРИСОВКА
    # ========================================================
    # Фон (земля)
    soil_r = int(40 * light + 35)
    soil_g = int(35 * light + 28)
    soil_b = int(25 * light + 20)
    screen.fill((soil_r, soil_g, soil_b))

    # Вода и растения (одним проходом)
    for y in range(H):
        for x in range(W):
            i = idx(x, y)
            p = plant[i]
            w = water[i]
            occ = occupancy[i]

            if occ == 0:  # ячейка свободна — рисуем воду/растение
                if p > 3:
                    v = p * 1.8
                    if v > 200: v = 200
                    cr = int(35 + 30 * light)
                    cg = int(90 + (60 + v) * light * 0.6)
                    cb = int(35 + 25 * light)
                    if cg > 230: cg = 230
                    draw_cell(x, y, (cr, cg, cb))
                elif w > 2:
                    v = w * 2.0
                    if v > 180: v = 180
                    cr = int(30 + 25 * light)
                    cg = int(80 + (70 + v / 2) * light * 0.5)
                    cb = int(120 + (140 + v) * light * 0.5)
                    if cb > 245: cb = 245
                    draw_cell(x, y, (cr, cg, cb))
            # Если ячейка занята животным — не рисуем фон, 
            # животное нарисуем отдельным проходом

    # Травоядные (жёлтые ячейки)
    hcr = int(180 + 50 * light)
    hcg = int(160 + 40 * light)
    hcb = int(70 + 30 * light)
    for hi in range(count_h):
        draw_cell(hgx[hi], hgy[hi], (hcr, hcg, hcb))

    # Хищники (красные ячейки)
    pcr = int(180 + 60 * light)
    pcg = int(50 + 30 * light)
    pcb = int(50 + 30 * light)
    for pi in range(count_p):
        draw_cell(pgx[pi], pgy[pi], (pcr, pcg, pcb))

    # ---------- HUD ----------
    hud_y = 10
    line_h = font_size + 5
    
    # Полоска дня/ночи
    bar_w = SW - 100
    bar_x = 50
    bar_h = max(6, font_size // 3)
    pygame.draw.rect(screen, (40, 40, 40), (bar_x, hud_y, bar_w, bar_h))
    pygame.draw.rect(screen, (230, 210, 110), (bar_x, hud_y, int(bar_w * cyc), bar_h))
    
    sun_x = bar_x + int(bar_w * cyc)
    sun_size = max(8, font_size // 2.5)
    sun_color = (255, 240, 130) if light > 0.5 else (200, 200, 230)
    pygame.draw.rect(screen, sun_color, 
                    (sun_x - sun_size//2, hud_y - sun_size//4, sun_size, sun_size))

    hud_y += bar_h + 10
    draw_text(f"Травоядные: {count_h}  (макс: {h_max_seen})",
             20, hud_y, (230, 200, 90))
    hud_y += line_h
    draw_text(f"Хищники:    {count_p}  (макс: {p_max_seen})",
             20, hud_y, (240, 100, 100))
    hud_y += line_h
    draw_text(f"Вода: {water_cells} ячеек  |  Сетка: {W}×{H} = {TOTAL}",
             20, hud_y, (130, 200, 255))

    draw_text("Касайтесь экрана — полив дождём",
             20, SH - font_size - 10, (200, 200, 200))
    draw_text("Выход: BACK / ESC",
             20, SH - font_size * 2 - 15, (150, 150, 150))

    pygame.display.flip()
    clock.tick(60)  # 15 тактов в секунду — наглядный пошаговый режим

pygame.quit()
