# -*- coding: utf-8 -*-

import math
import os
import random
import sys
import textwrap
from dataclasses import dataclass, field
from enum import Enum

import pygame

WIDTH = 1280
HEIGHT = 720
FALLBACK_FPS_LIMIT = 60

GROUND_Y = 462
GRAVITY = 0.68
MOVE_SPEED = 4.1
JUMP_SPEED = -13.2


class Scene(Enum):
    TITLE = "title"
    LETTER = "letter"
    PLAYING = "playing"
    QUIZ = "quiz"
    LEVEL_DONE = "level_done"
    ENDING = "ending"


@dataclass
class Question:
    prompt: str
    options: list[str]
    answer: int
    feedback: str


@dataclass
class Level:
    title: str
    theme: str
    letter_title: str
    letter_body: list[str]
    final_message: str
    questions: list[Question]
    platforms: list[pygame.Rect]
    coins: list[tuple[int, int]]
    gates: list[tuple[int, int]]
    color_top: tuple[int, int, int]
    color_bottom: tuple[int, int, int]
    accent: tuple[int, int, int]
    width: int = 2480


@dataclass
class Player:
    rect: pygame.Rect = field(default_factory=lambda: pygame.Rect(68, GROUND_Y - 56, 34, 56))
    vel: pygame.Vector2 = field(default_factory=lambda: pygame.Vector2(0, 0))
    on_ground: bool = False
    facing: int = 1
    blink: float = 0


class FiscalQuest:
    def __init__(self, headless: bool = False) -> None:
        self.headless = headless
        pygame.init()
        pygame.display.set_caption("Missão Fiscal")
        flags = pygame.HIDDEN if headless else 0
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
        self.max_fps = self.detect_refresh_rate()
        self.current_fps = 0.0
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 20)
        self.small_font = pygame.font.SysFont("consolas", 16)
        self.big_font = pygame.font.SysFont("consolas", 42, bold=True)
        self.title_font = pygame.font.SysFont("consolas", 58, bold=True)

        self.levels = build_levels()
        self.scene = Scene.TITLE
        self.level_index = 0
        self.player = Player()
        self.camera_x = 0
        self.score = 0
        self.lives = 3
        self.total_coins = 0
        self.collected: set[int] = set()
        self.gates_done: set[int] = set()
        self.current_question_index = 0
        self.quiz_feedback: str | None = None
        self.quiz_correct: bool | None = None
        self.quiz_gate_index: int | None = None
        self.quiz_option_order: list[int] = []
        self.message_timer = 0
        self.frame = 0
        self.sparkles: list[tuple[float, float, float, tuple[int, int, int]]] = []
        self.reset_level()

    def detect_refresh_rate(self) -> int:
        try:
            refresh_rate = pygame.display.get_current_refresh_rate()
        except (AttributeError, pygame.error):
            refresh_rate = 0

        if not refresh_rate:
            try:
                refresh_rates = pygame.display.get_desktop_refresh_rates()
            except (AttributeError, pygame.error):
                refresh_rates = []
            refresh_rate = max(refresh_rates, default=0)

        if not refresh_rate:
            refresh_rate = FALLBACK_FPS_LIMIT

        return max(30, int(round(refresh_rate)))

    @property
    def level(self) -> Level:
        return self.levels[self.level_index]

    def reset_level(self) -> None:
        self.player = Player()
        self.camera_x = 0
        self.collected = set()
        self.gates_done = set()
        self.current_question_index = 0
        self.quiz_feedback = None
        self.quiz_correct = None
        self.quiz_gate_index = None
        self.quiz_option_order = []
        self.total_coins = len(self.level.coins)
        self.message_timer = 120
        self.sparkles.clear()

    def run(self) -> None:
        while True:
            dt = self.clock.tick(self.max_fps) / 1000
            self.update_fps_counter()
            self.frame += 1
            events = pygame.event.get()
            for event in events:
                if event.type == pygame.QUIT:
                    pygame.quit()
                    return
            self.handle_events(events)
            self.update(dt)
            self.draw()
            pygame.display.flip()

    def smoke_test(self, frames: int = 180) -> None:
        for _ in range(frames):
            dt = self.clock.tick(self.max_fps) / 1000
            self.update_fps_counter()
            self.frame += 1
            self.handle_events([])
            self.update(dt)
            self.draw()
            pygame.display.flip()
        pygame.quit()

    def update_fps_counter(self) -> None:
        measured_fps = self.clock.get_fps()
        if measured_fps <= 0:
            return
        if self.current_fps <= 0:
            self.current_fps = measured_fps
        else:
            self.current_fps = self.current_fps * 0.88 + measured_fps * 0.12

    def handle_events(self, events: list[pygame.event.Event]) -> None:
        for event in events:
            if event.type != pygame.KEYDOWN:
                continue
            if event.key == pygame.K_ESCAPE:
                if self.scene == Scene.PLAYING:
                    self.scene = Scene.TITLE
                elif self.scene != Scene.TITLE:
                    self.scene = Scene.PLAYING
                continue
            if self.scene == Scene.TITLE:
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.scene = Scene.LETTER
            elif self.scene == Scene.LETTER:
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.scene = Scene.PLAYING
            elif self.scene == Scene.QUIZ:
                self.handle_quiz_key(event.key)
            elif self.scene == Scene.LEVEL_DONE:
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.advance_level()
            elif self.scene == Scene.ENDING:
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.level_index = 0
                    self.score = 0
                    self.lives = 3
                    self.reset_level()
                    self.scene = Scene.TITLE

    def handle_quiz_key(self, key: int) -> None:
        if self.quiz_feedback is not None:
            if key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.quiz_gate_index is not None:
                    self.gates_done.add(self.quiz_gate_index)
                self.quiz_feedback = None
                self.quiz_correct = None
                self.quiz_option_order = []
                self.scene = Scene.PLAYING
            return

        key_map = {
            pygame.K_1: 0,
            pygame.K_2: 1,
            pygame.K_3: 2,
            pygame.K_4: 3,
        }
        if key not in key_map:
            return
        choice = key_map[key]
        question = self.level.questions[self.current_question_index]
        if choice >= len(self.quiz_option_order):
            return
        selected_option = self.quiz_option_order[choice]
        if selected_option == question.answer:
            self.score += 120
            self.quiz_feedback = "Correto! " + question.feedback
            self.quiz_correct = True
            self.spawn_sparkles(self.player.rect.centerx, self.player.rect.top, (255, 234, 111))
        else:
            self.lives = max(1, self.lives - 1)
            self.quiz_feedback = "Quase! " + question.feedback
            self.quiz_correct = False

    def update(self, dt: float) -> None:
        if self.scene == Scene.PLAYING:
            self.update_player()
            self.update_camera()
            self.collect_coins()
            self.check_gates()
            self.check_finish()
        self.update_sparkles(dt)
        if self.message_timer > 0:
            self.message_timer -= 1

    def update_player(self) -> None:
        keys = pygame.key.get_pressed()
        self.player.vel.x = 0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.player.vel.x = -MOVE_SPEED
            self.player.facing = -1
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.player.vel.x = MOVE_SPEED
            self.player.facing = 1
        wants_jump = keys[pygame.K_SPACE] or keys[pygame.K_UP] or keys[pygame.K_w]
        if wants_jump and self.player.on_ground:
            self.player.vel.y = JUMP_SPEED
            self.player.on_ground = False

        self.player.vel.y += GRAVITY
        self.player.vel.y = min(self.player.vel.y, 16)

        self.move_and_collide(self.player.vel.x, 0)
        self.move_and_collide(0, self.player.vel.y)

        if self.player.rect.top > HEIGHT + 180:
            self.hurt_and_respawn()

    def move_and_collide(self, dx: float, dy: float) -> None:
        rect = self.player.rect
        rect.x += int(round(dx))
        rect.y += int(round(dy))

        if rect.left < 0:
            rect.left = 0
        if rect.right > self.level.width:
            rect.right = self.level.width

        solids = [pygame.Rect(0, GROUND_Y, self.level.width, HEIGHT - GROUND_Y)]
        solids.extend(self.level.platforms)
        if dy != 0:
            self.player.on_ground = False

        for solid in solids:
            if not rect.colliderect(solid):
                continue
            if dx > 0:
                rect.right = solid.left
            elif dx < 0:
                rect.left = solid.right
            elif dy > 0:
                rect.bottom = solid.top
                self.player.vel.y = 0
                self.player.on_ground = True
            elif dy < 0:
                rect.top = solid.bottom
                self.player.vel.y = 0

    def hurt_and_respawn(self) -> None:
        self.lives = max(1, self.lives - 1)
        self.player.rect.topleft = (64, GROUND_Y - 56)
        self.player.vel.update(0, 0)
        self.camera_x = 0
        self.message_timer = 120

    def update_camera(self) -> None:
        target = self.player.rect.centerx - WIDTH * 0.42
        self.camera_x += (target - self.camera_x) * 0.12
        self.camera_x = max(0, min(self.camera_x, self.level.width - WIDTH))

    def collect_coins(self) -> None:
        for index, (x, y) in enumerate(self.level.coins):
            if index in self.collected:
                continue
            coin_rect = pygame.Rect(x - 14, y - 14, 28, 28)
            if self.player.rect.colliderect(coin_rect):
                self.collected.add(index)
                self.score += 25
                self.spawn_sparkles(x, y, (255, 216, 72))

    def check_gates(self) -> None:
        for gate_index, (x, y) in enumerate(self.level.gates):
            if gate_index in self.gates_done:
                continue
            gate_rect = pygame.Rect(x - 22, y - 70, 44, 86)
            if self.player.rect.colliderect(gate_rect):
                self.quiz_gate_index = gate_index
                self.current_question_index = min(gate_index, len(self.level.questions) - 1)
                self.quiz_feedback = None
                self.quiz_correct = None
                self.shuffle_quiz_options()
                self.scene = Scene.QUIZ
                break

    def shuffle_quiz_options(self) -> None:
        question = self.level.questions[self.current_question_index]
        self.quiz_option_order = list(range(len(question.options)))
        random.shuffle(self.quiz_option_order)

        if len(self.quiz_option_order) > 1 and self.quiz_option_order.index(question.answer) == question.answer:
            swap_index = (question.answer + random.randrange(1, len(self.quiz_option_order))) % len(self.quiz_option_order)
            self.quiz_option_order[question.answer], self.quiz_option_order[swap_index] = (
                self.quiz_option_order[swap_index],
                self.quiz_option_order[question.answer],
            )

    def check_finish(self) -> None:
        finish_rect = pygame.Rect(self.level.width - 110, GROUND_Y - 112, 78, 112)
        if self.player.rect.colliderect(finish_rect) and len(self.gates_done) == len(self.level.gates):
            coin_bonus = int(250 * (len(self.collected) / max(1, self.total_coins)))
            self.score += coin_bonus
            self.scene = Scene.LEVEL_DONE

    def advance_level(self) -> None:
        if self.level_index + 1 >= len(self.levels):
            self.scene = Scene.ENDING
            return
        self.level_index += 1
        self.reset_level()
        self.scene = Scene.LETTER

    def spawn_sparkles(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        for _ in range(18):
            self.sparkles.append(
                (
                    x + random.uniform(-8, 8),
                    y + random.uniform(-8, 8),
                    random.uniform(0.5, 1.1),
                    color,
                )
            )

    def update_sparkles(self, dt: float) -> None:
        alive = []
        for x, y, life, color in self.sparkles:
            life -= dt * 1.7
            if life > 0:
                alive.append((x, y - dt * 32, life, color))
        self.sparkles = alive

    def draw(self) -> None:
        if self.scene == Scene.TITLE:
            self.draw_title()
        elif self.scene == Scene.LETTER:
            self.draw_letter()
        elif self.scene == Scene.PLAYING:
            self.draw_world()
            self.draw_hud()
        elif self.scene == Scene.QUIZ:
            self.draw_world()
            self.draw_hud()
            self.draw_quiz()
        elif self.scene == Scene.LEVEL_DONE:
            self.draw_level_done()
        elif self.scene == Scene.ENDING:
            self.draw_ending()
        self.draw_fps_counter()

    def draw_title(self) -> None:
        self.draw_gradient((22, 47, 77), (25, 135, 108))
        self.draw_title_city_silhouette()
        self.draw_big_coin(WIDTH // 2, 78, 34)
        self.center_text("MISSÃO FISCAL", self.title_font, (255, 249, 216), 154)
        self.center_text("Uma aventura 2D sobre cidadania e dinheiro público.", self.font, (231, 245, 238), 210)

        start_rect = pygame.Rect(0, 0, 278, 52)
        start_rect.center = (WIDTH // 2, 292)
        pygame.draw.rect(self.screen, (245, 198, 81), start_rect, border_radius=6)
        pygame.draw.rect(self.screen, (95, 73, 28), start_rect, 3, border_radius=6)
        self.center_text_at("JOGAR", self.big_font, (51, 43, 30), start_rect.centerx, start_rect.centery - 1)
        self.center_text("Setas/WASD: mover | Espaço: pular | 1-4: responder", self.small_font, (226, 245, 236), 352)

    def draw_letter(self) -> None:
        self.draw_gradient(self.level.color_top, self.level.color_bottom)
        self.draw_city_silhouette(0)
        panel = pygame.Rect(92, 58, WIDTH - 184, HEIGHT - 116)
        pygame.draw.rect(self.screen, (251, 242, 203), panel, border_radius=8)
        pygame.draw.rect(self.screen, (117, 85, 48), panel, 4, border_radius=8)
        pygame.draw.line(self.screen, (201, 164, 103), (panel.left + 28, panel.top + 86), (panel.right - 28, panel.top + 86), 2)
        self.draw_text(self.level.letter_title.upper(), self.big_font, (74, 59, 42), panel.left + 34, panel.top + 28)
        y = panel.top + 112
        for paragraph in self.level.letter_body:
            y = self.draw_wrapped(paragraph, self.font, (53, 49, 43), panel.left + 38, y, panel.width - 76, 27)
            y += 12
        self.center_text("ENTER", self.font, (84, 65, 38), panel.bottom - 56)

    def draw_world(self) -> None:
        self.draw_gradient(self.level.color_top, self.level.color_bottom)
        self.draw_sun()
        self.draw_city_silhouette(self.camera_x * 0.22)
        self.draw_clouds()
        self.draw_ground()
        self.draw_platforms()
        self.draw_coins()
        self.draw_gates()
        self.draw_finish()
        self.draw_player()
        self.draw_sparkles()
        if self.message_timer > 0 and self.scene == Scene.PLAYING:
            self.draw_stage_badge()

    def draw_gradient(self, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> None:
        for y in range(HEIGHT):
            t = y / HEIGHT
            color = (
                int(top[0] + (bottom[0] - top[0]) * t),
                int(top[1] + (bottom[1] - top[1]) * t),
                int(top[2] + (bottom[2] - top[2]) * t),
            )
            pygame.draw.line(self.screen, color, (0, y), (WIDTH, y))

    def draw_sun(self) -> None:
        x = int(790 - self.camera_x * 0.04)
        pygame.draw.circle(self.screen, (255, 229, 139), (x, 80), 42)
        pygame.draw.circle(self.screen, (255, 242, 179), (x, 80), 27)

    def draw_city_silhouette(self, offset: float) -> None:
        base = GROUND_Y
        colors = [(43, 77, 94), (35, 66, 82), (27, 54, 70)]
        for layer, color in enumerate(colors):
            speed = 0.16 + layer * 0.07
            spacing = 118 + layer * 18
            parallax = int(offset * speed)
            first_index = parallax // spacing - 3
            last_index = first_index + (WIDTH // spacing) + 8
            for index in range(first_index, last_index):
                seed = index * 97 + layer * 43
                w = 62 + abs(seed * 11) % 74
                h = 68 + abs(seed * 7) % 122
                x = index * spacing - parallax + (layer * 29) % 47
                rect = pygame.Rect(x, base - h - layer * 12, w, h + layer * 12)
                pygame.draw.rect(self.screen, color, rect)
                for wx in range(rect.left + 12, rect.right - 10, 24):
                    for wy in range(rect.top + 16, rect.bottom - 20, 30):
                        if (wx // 24 + wy // 30 + index + layer) % 3 == 0:
                            pygame.draw.rect(self.screen, (244, 212, 125), (wx, wy, 8, 10))

    def draw_title_city_silhouette(self) -> None:
        base = 466
        colors = [(28, 58, 75), (36, 76, 88), (43, 92, 93)]
        for layer, color in enumerate(colors):
            spacing = 118 + layer * 24
            y_offset = layer * 12
            for index in range(-2, WIDTH // spacing + 4):
                seed = index * 83 + layer * 41
                w = 64 + abs(seed * 7) % 62
                h = 44 + abs(seed * 5) % 48
                x = index * spacing + 18 + layer * 34
                rect = pygame.Rect(x, base - h + y_offset, w, h + 42)
                pygame.draw.rect(self.screen, color, rect)
                for wx in range(rect.left + 14, rect.right - 10, 26):
                    for wy in range(rect.top + 18, min(rect.bottom - 18, base - 8), 28):
                        if (wx // 26 + wy // 28 + index + layer) % 3 != 0:
                            pygame.draw.rect(self.screen, (247, 215, 112), (wx, wy, 8, 10))

        pygame.draw.rect(self.screen, (25, 141, 115), (0, base, WIDTH, HEIGHT - base))
        pygame.draw.rect(self.screen, (22, 118, 101), (0, base + 16, WIDTH, HEIGHT - base - 16))

    def draw_clouds(self) -> None:
        for i, (cx, cy) in enumerate([(220, 94), (510, 128), (840, 104), (1130, 148), (1510, 96), (1980, 130)]):
            x = int(cx - self.camera_x * 0.34) % (self.level.width // 2)
            if x > WIDTH + 90:
                x -= self.level.width // 2
            color = (238, 250, 245) if i % 2 else (225, 243, 239)
            pygame.draw.circle(self.screen, color, (x, cy), 22)
            pygame.draw.circle(self.screen, color, (x + 26, cy + 5), 28)
            pygame.draw.circle(self.screen, color, (x + 58, cy), 20)
            pygame.draw.rect(self.screen, color, (x, cy + 4, 62, 22), border_radius=10)

    def draw_ground(self) -> None:
        pygame.draw.rect(self.screen, (88, 143, 86), (0, GROUND_Y, WIDTH, HEIGHT - GROUND_Y))
        pygame.draw.rect(self.screen, (65, 112, 71), (0, GROUND_Y + 14, WIDTH, HEIGHT - GROUND_Y - 14))
        tile_w = 48
        start = -int(self.camera_x) % tile_w
        for x in range(start - tile_w, WIDTH + tile_w, tile_w):
            pygame.draw.line(self.screen, (104, 164, 94), (x, GROUND_Y), (x + 28, HEIGHT), 3)

    def draw_platforms(self) -> None:
        for platform in self.level.platforms:
            rect = self.world_rect(platform)
            pygame.draw.rect(self.screen, (94, 99, 71), rect, border_radius=4)
            pygame.draw.rect(self.screen, self.level.accent, (rect.x, rect.y, rect.width, 10), border_radius=4)
            pygame.draw.rect(self.screen, (47, 63, 55), rect, 2, border_radius=4)

    def draw_coins(self) -> None:
        for index, (x, y) in enumerate(self.level.coins):
            if index in self.collected:
                continue
            sx = int(x - self.camera_x)
            wobble = math.sin((self.frame + index * 13) * 0.08) * 3
            pygame.draw.circle(self.screen, (105, 75, 24), (sx + 2, int(y + wobble) + 2), 14)
            pygame.draw.circle(self.screen, (255, 214, 74), (sx, int(y + wobble)), 14)
            pygame.draw.circle(self.screen, (255, 241, 157), (sx - 4, int(y + wobble) - 4), 5)
            self.center_text_at("$", self.small_font, (91, 63, 19), sx, int(y + wobble) - 9)

    def draw_gates(self) -> None:
        for gate_index, (x, y) in enumerate(self.level.gates):
            if gate_index in self.gates_done:
                continue
            sx = int(x - self.camera_x)
            post = pygame.Rect(sx - 18, y - 64, 36, 78)
            pygame.draw.rect(self.screen, (82, 58, 48), post, border_radius=4)
            pygame.draw.rect(self.screen, (246, 237, 186), (post.x + 5, post.y + 7, 26, 42), border_radius=3)
            self.center_text_at("?", self.big_font, (49, 91, 110), sx, y - 60)
            pygame.draw.rect(self.screen, (51, 44, 41), post, 2, border_radius=4)

    def draw_finish(self) -> None:
        sx = int(self.level.width - 110 - self.camera_x)
        rect = pygame.Rect(sx, GROUND_Y - 112, 78, 112)
        pygame.draw.rect(self.screen, (80, 91, 116), rect, border_radius=3)
        pygame.draw.rect(self.screen, (235, 226, 191), (sx + 18, GROUND_Y - 70, 42, 70), border_radius=3)
        pygame.draw.polygon(self.screen, self.level.accent, [(sx - 10, GROUND_Y - 112), (sx + 39, GROUND_Y - 158), (sx + 88, GROUND_Y - 112)])
        pygame.draw.rect(self.screen, (38, 45, 58), rect, 2, border_radius=3)
        self.center_text_at("FIM", self.small_font, (255, 248, 216), sx + 39, GROUND_Y - 104)

    def draw_player(self) -> None:
        rect = self.world_rect(self.player.rect)
        pygame.draw.ellipse(self.screen, (30, 42, 50, 80), (rect.x - 5, rect.bottom - 5, rect.width + 10, 8))
        body = pygame.Rect(rect.x + 3, rect.y + 18, rect.width - 6, rect.height - 20)
        head = pygame.Rect(rect.x + 5, rect.y + 2, rect.width - 10, 24)
        pygame.draw.rect(self.screen, (33, 126, 142), body, border_radius=5)
        pygame.draw.rect(self.screen, (242, 196, 143), head, border_radius=5)
        pygame.draw.rect(self.screen, (248, 213, 89), (rect.x + 1, rect.y + 10, rect.width - 2, 9), border_radius=3)
        eye_x = head.centerx + 5 * self.player.facing
        pygame.draw.rect(self.screen, (35, 45, 53), (eye_x, head.y + 9, 4, 4))
        pygame.draw.rect(self.screen, (30, 70, 83), (body.x + 5, body.y + 8, body.width - 10, 10), border_radius=3)
        leg_y = rect.bottom - 10
        pygame.draw.rect(self.screen, (42, 65, 82), (rect.x + 5, leg_y, 9, 12), border_radius=2)
        pygame.draw.rect(self.screen, (42, 65, 82), (rect.right - 14, leg_y, 9, 12), border_radius=2)

    def draw_sparkles(self) -> None:
        for x, y, life, color in self.sparkles:
            sx = int(x - self.camera_x)
            radius = max(1, int(4 * life))
            pygame.draw.circle(self.screen, color, (sx, int(y)), radius)

    def draw_hud(self) -> None:
        bar = pygame.Rect(18, 16, WIDTH - 36, 44)
        pygame.draw.rect(self.screen, (23, 36, 44), bar, border_radius=8)
        pygame.draw.rect(self.screen, (84, 105, 111), bar, 2, border_radius=8)
        self.draw_text(f"Fase {self.level_index + 1}: {self.level.theme}", self.font, (244, 248, 232), 34, 28)
        self.draw_text(f"Recursos {len(self.collected)}/{self.total_coins}", self.font, (255, 222, 102), 430, 28)
        self.draw_text(f"Pontos {self.score}", self.font, (215, 244, 234), 650, 28)
        for i in range(self.lives):
            pygame.draw.circle(self.screen, (233, 83, 81), (890 + i * 20, 38), 7)

    def draw_fps_counter(self) -> None:
        fps_value = int(round(self.current_fps)) if self.current_fps > 0 else self.max_fps
        label = f"FPS {fps_value}/{self.max_fps}"
        surface = self.small_font.render(label, True, (224, 244, 234))
        box = surface.get_rect()
        box.bottomright = (WIDTH - 12, HEIGHT - 10)
        panel = box.inflate(14, 8)
        overlay = pygame.Surface(panel.size, pygame.SRCALPHA)
        overlay.fill((12, 24, 30, 170))
        self.screen.blit(overlay, panel.topleft)
        pygame.draw.rect(self.screen, (92, 130, 124), panel, 1, border_radius=4)
        self.screen.blit(surface, box)

    def draw_stage_badge(self) -> None:
        badge = pygame.Rect(260, 80, 440, 62)
        pygame.draw.rect(self.screen, (255, 250, 226), badge, border_radius=8)
        pygame.draw.rect(self.screen, (86, 75, 58), badge, 2, border_radius=8)
        self.center_text(self.level.title, self.font, (56, 51, 43), 94)

    def draw_quiz(self) -> None:
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((8, 16, 22, 172))
        self.screen.blit(shade, (0, 0))
        panel = pygame.Rect(112, 70, WIDTH - 224, HEIGHT - 140)
        pygame.draw.rect(self.screen, (247, 242, 220), panel, border_radius=8)
        pygame.draw.rect(self.screen, (77, 68, 55), panel, 4, border_radius=8)
        question = self.level.questions[self.current_question_index]
        self.draw_text("DESAFIO FISCAL", self.big_font, (48, 67, 76), panel.x + 28, panel.y + 22)
        y = self.draw_wrapped(question.prompt, self.font, (44, 45, 42), panel.x + 30, panel.y + 88, panel.width - 60, 28)
        y += 18

        option_order = self.quiz_option_order or list(range(len(question.options)))
        for index, option_index in enumerate(option_order):
            option_rect = pygame.Rect(panel.x + 36, y + index * 52, panel.width - 72, 40)
            color = (255, 255, 244)
            if self.quiz_feedback is not None:
                color = (226, 245, 224) if option_index == question.answer else (255, 255, 244)
            pygame.draw.rect(self.screen, color, option_rect, border_radius=5)
            pygame.draw.rect(self.screen, (114, 106, 86), option_rect, 2, border_radius=5)
            option = question.options[option_index]
            label = f"{index + 1}. {option}"
            self.draw_text(label, self.font, (40, 43, 39), option_rect.x + 14, option_rect.y + 9)

        if self.quiz_feedback:
            feedback_rect = pygame.Rect(panel.x + 36, panel.bottom - 78, panel.width - 72, 48)
            fill = (224, 244, 226) if self.quiz_correct else (255, 231, 213)
            pygame.draw.rect(self.screen, fill, feedback_rect, border_radius=5)
            pygame.draw.rect(self.screen, (102, 92, 73), feedback_rect, 2, border_radius=5)
            self.draw_wrapped(self.quiz_feedback, self.small_font, (45, 43, 39), feedback_rect.x + 12, feedback_rect.y + 7, feedback_rect.width - 24, 19)

    def draw_level_done(self) -> None:
        self.draw_gradient(self.level.color_top, self.level.color_bottom)
        self.draw_city_silhouette(0)
        panel = pygame.Rect(136, 86, WIDTH - 272, HEIGHT - 172)
        pygame.draw.rect(self.screen, (248, 246, 226), panel, border_radius=8)
        pygame.draw.rect(self.screen, (77, 74, 61), panel, 4, border_radius=8)
        self.center_text("MISSÃO CUMPRIDA!", self.big_font, (47, 73, 82), panel.y + 36)
        self.draw_wrapped(self.level.final_message, self.font, (50, 50, 43), panel.x + 42, panel.y + 104, panel.width - 84, 30)
        self.center_text(f"Recursos coletados: {len(self.collected)}/{self.total_coins}", self.font, (117, 83, 25), panel.y + 226)
        self.center_text(f"Pontuação atual: {self.score}", self.font, (42, 79, 84), panel.y + 260)
        self.center_text("ENTER", self.font, (66, 58, 43), panel.bottom - 58)

    def draw_ending(self) -> None:
        self.draw_gradient((21, 49, 73), (25, 123, 93))
        self.draw_city_silhouette(0)
        self.draw_big_coin(WIDTH // 2, 118, 46)
        self.center_text("CIDADE TRANSFORMADA", self.big_font, (255, 248, 216), 184)
        lines = [
            "Você aprendeu que impostos financiam serviços públicos,",
            "que a nota fiscal ajuda a combater a sonegação,",
            "e que todo cidadão pode acompanhar o dinheiro público.",
        ]
        y = 242
        for line in lines:
            self.center_text(line, self.font, (230, 245, 236), y)
            y += 34
        self.center_text(f"Pontuação final: {self.score}", self.big_font, (255, 222, 102), 382)
        self.center_text("ENTER", self.font, (226, 245, 236), 456)

    def draw_big_coin(self, x: int, y: int, radius: int) -> None:
        pygame.draw.circle(self.screen, (111, 72, 16), (x + 5, y + 5), radius)
        pygame.draw.circle(self.screen, (255, 210, 67), (x, y), radius)
        pygame.draw.circle(self.screen, (255, 241, 158), (x - 13, y - 13), radius // 4)
        self.center_text_at("$", self.title_font, (103, 70, 20), x, y - 28)

    def world_rect(self, rect: pygame.Rect) -> pygame.Rect:
        return pygame.Rect(int(rect.x - self.camera_x), rect.y, rect.width, rect.height)

    def center_text(self, text: str, font: pygame.font.Font, color: tuple[int, int, int], y: int) -> None:
        surface = font.render(text, True, color)
        self.screen.blit(surface, surface.get_rect(center=(WIDTH // 2, y)))

    def center_text_at(self, text: str, font: pygame.font.Font, color: tuple[int, int, int], x: int, y: int) -> None:
        surface = font.render(text, True, color)
        self.screen.blit(surface, surface.get_rect(center=(x, y)))

    def draw_text(self, text: str, font: pygame.font.Font, color: tuple[int, int, int], x: int, y: int) -> None:
        surface = font.render(text, True, color)
        self.screen.blit(surface, (x, y))

    def draw_wrapped(
        self,
        text: str,
        font: pygame.font.Font,
        color: tuple[int, int, int],
        x: int,
        y: int,
        width: int,
        line_height: int,
    ) -> int:
        words_per_line = max(24, width // 11)
        for line in textwrap.wrap(text, words_per_line):
            while font.size(line)[0] > width and len(line) > 8:
                line = line[:-1]
            self.draw_text(line, font, color, x, y)
            y += line_height
        return y


def build_levels() -> list[Level]:
    common_platforms = [
        pygame.Rect(280, 362, 150, 22),
        pygame.Rect(560, 310, 150, 22),
        pygame.Rect(820, 386, 180, 22),
        pygame.Rect(1120, 330, 180, 22),
        pygame.Rect(1430, 374, 160, 22),
        pygame.Rect(1710, 314, 190, 22),
        pygame.Rect(2020, 360, 150, 22),
    ]
    common_coins = [
        (326, 326),
        (382, 326),
        (600, 274),
        (662, 274),
        (878, 350),
        (948, 350),
        (1165, 294),
        (1235, 294),
        (1480, 338),
        (1538, 338),
        (1760, 278),
        (1830, 278),
        (2070, 324),
        (2130, 324),
        (2310, 420),
    ]
    gates = [(760, GROUND_Y), (1370, GROUND_Y), (1960, GROUND_Y)]

    return [
        Level(
            title="A cidade precisa de você",
            theme="Impostos e serviços públicos",
            letter_title="Carta da Fase 1",
            letter_body=[
                "Olá, estudante! Você já reparou que a escola, a pracinha, o posto de saúde e a iluminação das ruas precisam de dinheiro para funcionar?",
                "Parte desse dinheiro vem dos impostos. Quando eles são arrecadados e usados corretamente, voltam para a população em forma de serviços públicos.",
                "Nesta fase, colete recursos públicos e responda aos desafios para ajudar a reconstruir a praça da cidade.",
            ],
            final_message="A praça recebeu luz, limpeza e brinquedos novos. Quando a arrecadação vira serviço público, toda a comunidade ganha.",
            questions=[
                Question(
                    "Para que os impostos podem ser usados quando são bem administrados?",
                    ["Serviços públicos como escola e saúde", "Somente prêmios individuais", "Comprar itens secretos", "Apagar documentos"],
                    0,
                    "Impostos financiam ações e serviços que atendem à coletividade.",
                ),
                Question(
                    "Quem se beneficia quando uma escola pública melhora com recursos arrecadados?",
                    ["Apenas a prefeitura", "Toda a comunidade escolar", "Só quem joga mais", "Ninguém"],
                    1,
                    "Educação de qualidade fortalece alunos, famílias e comunidade.",
                ),
                Question(
                    "O dinheiro público deve ser usado pensando em que objetivo?",
                    ["No interesse coletivo", "Em esconder gastos", "Em privilégios pessoais", "Em deixar a cidade parada"],
                    0,
                    "O recurso público existe para atender às necessidades da sociedade.",
                ),
            ],
            platforms=common_platforms,
            coins=common_coins,
            gates=gates,
            color_top=(101, 185, 209),
            color_bottom=(180, 221, 186),
            accent=(240, 189, 84),
        ),
        Level(
            title="O mistério da nota fiscal",
            theme="Nota fiscal e sonegação",
            letter_title="Carta da Fase 2",
            letter_body=[
                "A nota fiscal registra uma compra ou venda. Ela ajuda a provar que a operação aconteceu e que os impostos daquela venda podem ser calculados.",
                "Quando alguém vende e não registra, pode acontecer sonegação. Isso diminui os recursos que poderiam voltar em escolas, ruas, hospitais e projetos sociais.",
                "Nesta fase, siga os recibos dourados e mostre que pedir nota fiscal também é uma atitude cidadã.",
            ],
            final_message="As vendas foram registradas e os recursos chegaram ao caixa da cidade. Pedir nota fiscal ajuda a combater a sonegação.",
            questions=[
                Question(
                    "Por que pedir nota fiscal é importante?",
                    ["Porque registra a venda", "Porque aumenta o preço sem motivo", "Porque substitui estudar", "Porque esconde impostos"],
                    0,
                    "A nota fiscal formaliza a operação e ajuda na correta arrecadação.",
                ),
                Question(
                    "O que pode acontecer quando uma venda não é registrada?",
                    ["Sonegação", "Mais transparência", "Melhor controle social", "A escola recebe automaticamente"],
                    0,
                    "Sem registro, o imposto pode deixar de ser recolhido corretamente.",
                ),
                Question(
                    "Pedir nota fiscal é uma forma de participar da cidadania?",
                    ["Sim", "Não, nunca", "Só em jogos", "Só fora da escola"],
                    0,
                    "Pequenas atitudes também ajudam a cuidar do dinheiro público.",
                ),
            ],
            platforms=[
                pygame.Rect(250, 372, 150, 22),
                pygame.Rect(510, 326, 170, 22),
                pygame.Rect(790, 276, 130, 22),
                pygame.Rect(1060, 372, 180, 22),
                pygame.Rect(1340, 316, 160, 22),
                pygame.Rect(1630, 364, 180, 22),
                pygame.Rect(1960, 312, 170, 22),
            ],
            coins=[
                (294, 336),
                (354, 336),
                (555, 290),
                (628, 290),
                (832, 240),
                (882, 240),
                (1115, 336),
                (1190, 336),
                (1390, 280),
                (1452, 280),
                (1680, 328),
                (1750, 328),
                (2010, 276),
                (2080, 276),
                (2280, 420),
            ],
            gates=gates,
            color_top=(72, 141, 176),
            color_bottom=(221, 181, 132),
            accent=(111, 203, 183),
        ),
        Level(
            title="Olhos abertos na prefeitura",
            theme="Transparência e controle social",
            letter_title="Carta da Fase 3",
            letter_body=[
                "Depois que o dinheiro público é arrecadado, ele precisa ser planejado, gasto com responsabilidade e acompanhado pela sociedade.",
                "Transparência significa deixar as informações acessíveis. Controle social é quando os cidadãos acompanham, perguntam, cobram e participam das decisões.",
                "Nesta fase, leve os recursos até a prefeitura e mostre que fiscalizar também é cuidar da cidade.",
            ],
            final_message="A comunidade acompanhou os gastos, fez perguntas e escolheu prioridades. Cidadania também é participar depois que o imposto foi pago.",
            questions=[
                Question(
                    "O que significa transparência no uso do dinheiro público?",
                    ["Informações acessíveis à população", "Gastos escondidos", "Decisões sem explicação", "Pontuação secreta"],
                    0,
                    "Transparência permite que as pessoas acompanhem o que foi feito.",
                ),
                Question(
                    "Controle social acontece quando o cidadão...",
                    ["Acompanha e cobra o uso correto dos recursos", "Ignora os gastos", "Nunca participa", "Esconde a nota fiscal"],
                    0,
                    "Participar e fiscalizar fortalece a democracia.",
                ),
                Question(
                    "Qual atitude combina com educação fiscal?",
                    ["Perguntar como o dinheiro público foi usado", "Aceitar tudo sem olhar", "Destruir registros", "Valorizar a sonegação"],
                    0,
                    "Educação fiscal ensina direitos, deveres e acompanhamento do bem comum.",
                ),
            ],
            platforms=[
                pygame.Rect(280, 346, 170, 22),
                pygame.Rect(600, 392, 160, 22),
                pygame.Rect(890, 322, 170, 22),
                pygame.Rect(1170, 276, 150, 22),
                pygame.Rect(1460, 350, 180, 22),
                pygame.Rect(1760, 300, 160, 22),
                pygame.Rect(2050, 370, 150, 22),
            ],
            coins=[
                (330, 310),
                (396, 310),
                (646, 356),
                (714, 356),
                (940, 286),
                (1010, 286),
                (1215, 240),
                (1276, 240),
                (1512, 314),
                (1588, 314),
                (1810, 264),
                (1872, 264),
                (2100, 334),
                (2160, 334),
                (2310, 420),
            ],
            gates=gates,
            color_top=(67, 108, 151),
            color_bottom=(153, 200, 169),
            accent=(239, 117, 99),
        ),
    ]


def main() -> None:
    headless = "--smoke-test" in sys.argv
    if headless:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    game = FiscalQuest(headless=headless)
    if headless:
        game.smoke_test()
    else:
        game.run()


if __name__ == "__main__":
    main()
