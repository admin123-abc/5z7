from __future__ import annotations

import math, threading, time, struct, random, os
import pygame, pygame.gfxdraw
from typing import Optional, List
import config as C

_BOARD_AREA_W = C.GUI_WINDOW_W - C.GUI_SIDE_PANEL_W
_BOARD_AREA_H = C.GUI_WINDOW_H
_CELL = (_BOARD_AREA_W - 2 * C.GUI_BOARD_MARGIN) // (C.BOARD_SIZE - 1)
_ORIGIN_X = C.GUI_BOARD_MARGIN + (_BOARD_AREA_W - 2*C.GUI_BOARD_MARGIN - _CELL*(C.BOARD_SIZE-1))//2
_ORIGIN_Y = C.GUI_BOARD_MARGIN + (_BOARD_AREA_H - 2*C.GUI_BOARD_MARGIN - _CELL*(C.BOARD_SIZE-1))//2
_PIECE_R = int(_CELL * 0.44)

# ── 技能名称映射 ───────────────────────────────────────────
_SKILL_NAMES = {
    "horse": "一马当先",
    "swap":  "乾坤挪移",
    "void":  "终归虚无",
}
_SKILL_DESCS = {
    "horse": "下两颗斜连棋",
    "swap":  "翻转对手棋子",
    "void":  "清空3×3区域",
}
_SKILL_COLORS = {
    "horse": (100, 200, 255),
    "swap":  (255, 180, 60),
    "void":  (180, 80, 255),
}

# ── 音效合成 ───────────────────────────────────────────────
def _synth(freq=880, dur=0.07, vol=0.35, sr=44100):
    n = int(sr * dur); buf = bytearray()
    for i in range(n):
        t = i / sr; env = math.exp(-20*t)
        v = env*(0.7*math.sin(2*math.pi*freq*t)+0.3*math.sin(2*math.pi*freq*2.3*t))
        s = max(-32768, min(32767, int(v*vol*32767)))
        buf += struct.pack('<h', s)
    return pygame.mixer.Sound(buffer=bytes(buf))

# ── 木纹背景 ──────────────────────────────────────────────
def _make_board_texture(w, h):
    surf = pygame.Surface((w, h))
    bl, bd = C.GUI_COLOR_BOARD_LIGHT, C.GUI_COLOR_BOARD_DARK
    for y in range(h):
        for x in range(w):
            g = math.sin((x*0.03+y*0.008)*math.pi)*0.5+0.5
            s = math.sin((x*0.015-y*0.025)*math.pi)*0.5+0.5
            t = g*0.65+s*0.35
            r=int(bl[0]*t+bd[0]*(1-t)); gc=int(bl[1]*t+bd[1]*(1-t)); b=int(bl[2]*t+bd[2]*(1-t))
            dx=(x/w-0.5)*2; dy=(y/h-0.5)*2; vi=1.0-0.25*(dx*dx+dy*dy)
            surf.set_at((x,y),(max(0,min(255,int(r*vi))),max(0,min(255,int(gc*vi))),max(0,min(255,int(b*vi)))))
    return surf

# ── 程序化棋子绘制 ────────────────────────────────────────
def _draw_piece(surf, cx, cy, radius, is_black, alpha=255):
    if radius <= 0: return
    tmp = pygame.Surface((radius*2+8, radius*2+8), pygame.SRCALPHA)
    ox, oy = radius+4, radius+4
    if is_black:
        base,shine,shadow = C.GUI_BLACK_BASE, C.GUI_BLACK_SHINE, C.GUI_BLACK_SHADOW
        soff = (-radius//4, -radius//4)
    else:
        base,shine,shadow = C.GUI_WHITE_BASE, C.GUI_WHITE_SHINE, C.GUI_WHITE_SHADOW
        soff = (-radius//3, -radius//3)
    sh = pygame.Surface((radius*2+8, radius*2+8), pygame.SRCALPHA)
    for r in range(radius, 0, -1):
        pygame.gfxdraw.filled_circle(sh, ox+3, oy+4, r, (*shadow, int(60*(r/radius))))
    tmp.blit(sh, (0,0))
    for r in range(radius, 0, -1):
        t=r/radius
        pygame.gfxdraw.filled_circle(tmp, ox, oy, r,
            (int(shadow[0]*t+base[0]*(1-t)),int(shadow[1]*t+base[1]*(1-t)),int(shadow[2]*t+base[2]*(1-t)),alpha))
    pygame.gfxdraw.aacircle(tmp, ox, oy, radius, (*shadow, alpha))
    hx,hy=ox+soff[0],oy+soff[1]; sr2=max(1,radius//3)
    for r in range(sr2, 0, -1):
        t=1-r/sr2; a=int(200*(1-t*t)*(alpha/255))
        pygame.gfxdraw.filled_circle(tmp, hx, hy, r, (*shine, a))
    surf.blit(tmp, (cx-ox, cy-oy))

def _glow_line(surf, p1, p2, color, width=5):
    tmp = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    for w,a in [(width+8,40),(width+4,80),(width,200)]:
        pygame.draw.line(tmp, (*color, a), p1, p2, w)
    surf.blit(tmp, (0,0))


class GUIView:
    def __init__(self):
        pygame.init()
        if C.GUI_SOUND_ENABLED:
            try:
                pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
                self._snd_win = _synth(523, 0.3, 0.5)
                self._snd_skill = _synth(660, 0.12, 0.3)
                self._snd_undo  = _synth(330, 0.15, 0.25)
            except Exception:
                self._snd_win = self._snd_skill = self._snd_undo = None
        else:
            self._snd_win = self._snd_skill = self._snd_undo = None

        self._screen = pygame.display.set_mode((C.GUI_WINDOW_W, C.GUI_WINDOW_H))
        pygame.display.set_caption(C.GUI_WINDOW_TITLE)
        self._clock = pygame.time.Clock()
        self._ft = self._lf(28, True); self._fn = self._lf(18); self._fs = self._lf(14)
        self._fl = self._lf(44, True); self._fc = self._lf(12); self._fxs = self._lf(11)
        self._board_tex = _make_board_texture(_BOARD_AREA_W, _BOARD_AREA_H)

        # ── 状态 ─────────────────────────────────────────────
        self._board_snap = None; self._message = ""; self._last_move = None
        self._hover = None; self._win_line = None; self._game_over = False
        self._game_result = ""; self._ai_thinking = False
        self._current_piece = C.BLACK; self._move_count = 0
        self._t0 = time.time(); self._overlay_a = 0
        self._lock = threading.Lock()
        self._engine_thread = None; self._engine_ref = None
        self._drop_anims: list = []
        self._DROP_DUR = 0.22
        # 技能特效动画队列: [(type, cx, cy, start_time)]
        self._skill_fx: list = []

        # ── 技能状态机 ───────────────────────────────────────
        # None / "horse_first" / "horse_second" / "swap" / "void"
        self._skill_mode: Optional[str] = None
        self._horse_first: Optional[tuple] = None   # 一马当先第一落点
        self._skill_flash: Optional[str] = None     # 当前闪烁技能名
        self._skill_flash_t: float = 0.0

        # ── 外部资源 ─────────────────────────────────────────
        self._piece_img_player = self._load_piece_img(C.SRC_PLAYER_PIECE)
        self._piece_img_ai     = self._load_piece_img(C.SRC_AI_PIECE)
        self._piece_img_cache: dict = {}
        self._snd_player = self._load_sound(C.SRC_PLAYER_SOUND)
        self._snd_ai     = self._load_sound(C.SRC_AI_SOUND)
        self._piece_owner: dict = {}

        # ── 侧边栏技能按钮布局（运行时计算）────────────────
        self._btn_rects: dict = {}  # {"undo": Rect, "horse": Rect, ...}

    # ─────────────────────────────────────────────────────────
    # 主菜单
    # ─────────────────────────────────────────────────────────
    def show_menu(self) -> Optional[str]:
        buttons = [
            ("pve", "人机对战", "人类(黑) vs AI(白)"),
            ("pvp", "双人对战", "玩家1 vs 玩家2"),
            ("eve", "AI 自战",  "AI(黑) vs AI(白)"),
        ]
        btn_w, btn_h = 360, 70; gap = 20
        total_h = len(buttons)*btn_h + (len(buttons)-1)*gap
        start_y = (C.GUI_WINDOW_H - total_h)//2 + 60

        while True:
            self._clock.tick(C.GUI_FPS)
            t = time.time()-self._t0; mx,my = pygame.mouse.get_pos()
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT: pygame.quit(); return None
                if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                    pygame.quit(); return None
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    for i,(mode,_,_) in enumerate(buttons):
                        bx=(C.GUI_WINDOW_W-btn_w)//2; by=start_y+i*(btn_h+gap)
                        if bx<=mx<=bx+btn_w and by<=my<=by+btn_h: return mode
            self._screen.fill(C.GUI_COLOR_BG)
            title = self._fl.render("五子棋", True, C.GUI_COLOR_ACCENT)
            self._screen.blit(title, ((C.GUI_WINDOW_W-title.get_width())//2, 80))
            sub = self._fn.render("G   O   B   A   N   G", True, C.GUI_COLOR_TEXT_DIM)
            self._screen.blit(sub, ((C.GUI_WINDOW_W-sub.get_width())//2, 140))
            lw=300; lx=(C.GUI_WINDOW_W-lw)//2
            pygame.draw.line(self._screen, C.GUI_COLOR_PANEL_BORDER, (lx,180),(lx+lw,180),1)
            for i,(dx,dy,is_b) in enumerate([(120,300,True),(860,250,False),(200,600,True),(750,550,False)]):
                bob=math.sin(t*1.5+i*1.2)*8
                _draw_piece(self._screen, dx, int(dy+bob), 18, is_b, 80)
            for i,(mode,label,desc) in enumerate(buttons):
                bx=(C.GUI_WINDOW_W-btn_w)//2; by=start_y+i*(btn_h+gap)
                is_hover = bx<=mx<=bx+btn_w and by<=my<=by+btn_h
                bs = pygame.Surface((btn_w,btn_h), pygame.SRCALPHA)
                if is_hover:
                    pulse=abs(math.sin(t*3))*0.15+0.85
                    bg=tuple(int(c*pulse) for c in C.GUI_COLOR_ACCENT)+(60,)
                    bc=C.GUI_COLOR_ACCENT
                else:
                    bg=(*C.GUI_COLOR_PANEL_BG,180); bc=C.GUI_COLOR_PANEL_BORDER
                pygame.draw.rect(bs, bg,(0,0,btn_w,btn_h),border_radius=14)
                pygame.draw.rect(bs, (*bc,200),(0,0,btn_w,btn_h),2,border_radius=14)
                self._screen.blit(bs,(bx,by))
                tc=C.GUI_COLOR_ACCENT if is_hover else C.GUI_COLOR_TEXT_MAIN
                lt=self._fn.render(label,True,tc); dt=self._fs.render(desc,True,C.GUI_COLOR_TEXT_DIM)
                self._screen.blit(lt,(bx+(btn_w-lt.get_width())//2,by+12))
                self._screen.blit(dt,(bx+(btn_w-dt.get_width())//2,by+42))
            hint=self._fs.render("ESC 退出  |  点击选择模式",True,C.GUI_COLOR_TEXT_DIM)
            self._screen.blit(hint,((C.GUI_WINDOW_W-hint.get_width())//2,C.GUI_WINDOW_H-40))
            pygame.display.flip()

    # ─────────────────────────────────────────────────────────
    # View 协议
    # ─────────────────────────────────────────────────────────
    def render(self, board):
        new_piece = None
        with self._lock:
            old = self._board_snap
            self._board_snap = board.copy()
            if old is not None:
                for r in range(board.size):
                    for c in range(board.size):
                        if board.get(r,c) != C.EMPTY and old.get(r,c) == C.EMPTY:
                            new_piece = board.get(r,c)
                            self._drop_anims.append((r,c,new_piece,time.time()))
                            self._last_move = (r,c); self._move_count += 1
        if new_piece is not None and C.GUI_SOUND_ENABLED:
            owner = self._piece_owner.get(new_piece,"player")
            snd = self._snd_player if owner=="player" else self._snd_ai
            if snd:
                try: snd.play()
                except: pass

    def show_message(self, msg):
        with self._lock:
            self._message = msg
            if "黑子" in msg and "请落子" in msg:
                self._current_piece = C.BLACK; self._ai_thinking = False
            elif "白子" in msg and "请落子" in msg:
                self._current_piece = C.WHITE; self._ai_thinking = False
            if "获胜" in msg or "平局" in msg:
                self._game_over = True; self._game_result = msg.strip()
                if self._board_snap and self._last_move:
                    self._detect_win_line(self._board_snap)
                if self._snd_win:
                    try: self._snd_win.play()
                    except: pass

    def set_engine(self, engine):
        self._engine_ref = engine
        from agents.gui_human import GUIHumanPlayer
        from agents.human import HumanPlayer
        for piece,player in engine._players.items():
            if isinstance(player,(GUIHumanPlayer,HumanPlayer)):
                self._piece_owner[piece]="player"
            else:
                self._piece_owner[piece]="ai"
        self._engine_thread = threading.Thread(target=self._run_engine, daemon=True)
        self._engine_thread.start()

    def _run_engine(self):
        try: self._engine_ref.run()
        except SystemExit: pass
        except Exception as e:
            with self._lock:
                self._game_over=True; self._game_result=str(e)

    # ─────────────────────────────────────────────────────────
    # 主循环
    # ─────────────────────────────────────────────────────────
    def main_loop(self):
        while True:
            self._clock.tick(C.GUI_FPS)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT: pygame.quit(); raise SystemExit(0)
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        # 按 ESC 取消技能模式，或退出
                        if self._skill_mode:
                            self._skill_mode = None; self._horse_first = None
                        else:
                            pygame.quit(); raise SystemExit(0)
                    if ev.key == pygame.K_z:
                        self._try_undo()
                if ev.type == pygame.MOUSEMOTION:
                    self._hover = self._px2bd(ev.pos)
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    self._handle_click(ev.pos)
            self._update_ai()
            self._draw_frame()
            pygame.display.flip()

    def _handle_click(self, pos):
        """统一处理鼠标点击：侧边栏按钮 / 棋盘落子 / 技能选格。"""
        # 检查侧边栏按钮
        for btn_id, rect in self._btn_rects.items():
            if rect.collidepoint(pos):
                self._on_btn(btn_id); return

        if self._game_over: return

        rc = self._px2bd(pos)
        if rc is None: return

        # 技能模式下的点击
        if self._skill_mode:
            self._on_skill_click(*rc); return

        # 普通落子
        self._on_click(*rc)

    def _update_ai(self):
        from agents.gui_human import GUIHumanPlayer
        if not self._engine_ref or self._game_over: self._ai_thinking=False; return
        p = self._engine_ref._players.get(self._current_piece)
        self._ai_thinking = not isinstance(p, GUIHumanPlayer) and self._engine_thread and self._engine_thread.is_alive()

    # ─────────────────────────────────────────────────────────
    # 按钮事件
    # ─────────────────────────────────────────────────────────
    def _on_btn(self, btn_id: str):
        if self._game_over: return
        if not self._is_human_turn(): return

        if btn_id == "undo":
            self._try_undo()
        elif btn_id in ("horse", "swap", "void"):
            if self._engine_ref and self._engine_ref.skill_charges.get(btn_id, 0) > 0:
                # 切换技能模式
                if self._skill_mode == btn_id + ("_first" if btn_id=="horse" else ""):
                    self._skill_mode = None; self._horse_first = None
                else:
                    self._skill_mode = "horse_first" if btn_id=="horse" else btn_id
                    self._horse_first = None
                    self._skill_flash = btn_id
                    self._skill_flash_t = time.time()

    def _try_undo(self):
        if not self._is_human_turn(): return
        from agents.gui_human import GUIHumanPlayer
        if not self._engine_ref: return
        cp = self._current_piece
        player = self._engine_ref._players.get(cp)
        if isinstance(player, GUIHumanPlayer) and player.is_waiting():
            player.submit_undo()
            if self._snd_undo:
                try: self._snd_undo.play()
                except: pass
            self._skill_mode = None; self._horse_first = None

    def _is_human_turn(self) -> bool:
        from agents.gui_human import GUIHumanPlayer
        from agents.human import HumanPlayer
        if not self._engine_ref: return False
        p = self._engine_ref._players.get(self._current_piece)
        return isinstance(p, (GUIHumanPlayer, HumanPlayer))

    # ─────────────────────────────────────────────────────────
    # 技能点击处理
    # ─────────────────────────────────────────────────────────
    def _on_skill_click(self, row: int, col: int):
        engine = self._engine_ref
        if not engine: return

        if self._skill_mode == "horse_first":
            # 选第一落点：必须是空格
            with self._lock:
                snap = self._board_snap
            if snap and snap.is_valid_move(row, col):
                self._horse_first = (row, col)
                self._skill_mode = "horse_second"
            return

        if self._skill_mode == "horse_second":
            if self._horse_first is None: return
            r1,c1 = self._horse_first
            # 第二落点必须是 (r1±1, c1±1) 中的一个空格
            dr,dc = row-r1, col-c1
            if abs(dr)==1 and abs(dc)==1:
                ok = engine.skill_horse(r1, c1, dr, dc)
                if ok:
                    self._add_skill_fx("horse", row, col)
                    self._add_skill_fx("horse", r1, c1)
                    self._skill_mode = None; self._horse_first = None
                    self._after_skill(engine)
                    self._notify_human_dummy(engine)
            return

        if self._skill_mode == "swap":
            opp = C.WHITE if self._current_piece==C.BLACK else C.BLACK
            with self._lock:
                snap = self._board_snap
            if snap and snap.get(row,col)==opp:
                ok = engine.skill_swap(row, col)
                if ok:
                    self._add_skill_fx("swap", row, col)
                    self._skill_mode = None
                    self._after_skill(engine)
                    self._notify_human_dummy(engine)
            return

        if self._skill_mode == "void":
            ok = engine.skill_void(row, col)
            if ok:
                self._add_skill_fx("void", row, col)
                self._skill_mode = None
                self._after_skill(engine)
                self._notify_human_dummy(engine)
            return

    def _after_skill(self, engine):
        """技能生效后：更新棋盘快照、播音效、render。"""
        self.render(engine.board)
        if self._snd_skill:
            try: self._snd_skill.play()
            except: pass
        # 检查技能后是否有人赢了
        winner = engine.board.check_win_full()
        if winner != C.EMPTY:
            from config import PIECE_NAMES
            pname = PIECE_NAMES[winner]
            pplayer = engine._players[winner]
            self.view_render_force(engine.board)
            self.show_message(f"\n🎉 【{pname}】{pplayer.name} 获胜！游戏结束。")

    def view_render_force(self, board):
        with self._lock:
            self._board_snap = board.copy()

    def _notify_human_dummy(self, engine):
        """
        技能使用后，不切换回合，但玩家仍需正常落子。
        GUIHumanPlayer 还在 wait()，不需要做任何事。
        实际上技能不走引擎循环，所以不需要 submit。
        技能用完后还需要继续等待引擎给出 get_move 请求。
        但由于引擎在后台线程阻塞 get_move()，技能直接改棋盘：
        这里什么都不做，玩家继续点棋盘落子即可。
        """
        pass

    # ─────────────────────────────────────────────────────────
    # 坐标 + 普通落子
    # ─────────────────────────────────────────────────────────
    def _px2bd(self, pos):
        with self._lock:
            snap = self._board_snap
        if not snap: return None
        x,y = pos; thresh=_CELL*0.45
        col=round((x-_ORIGIN_X)/_CELL); row=round((y-_ORIGIN_Y)/_CELL)
        px=_ORIGIN_X+col*_CELL; py=_ORIGIN_Y+row*_CELL
        if math.hypot(x-px,y-py)>thresh: return None
        if not (0<=row<snap.size and 0<=col<snap.size): return None
        return row,col

    def _bd2px(self,r,c): return (_ORIGIN_X+c*_CELL, _ORIGIN_Y+r*_CELL)

    def _on_click(self, row, col):
        from agents.gui_human import GUIHumanPlayer
        if not self._engine_ref: return
        p = self._engine_ref._players.get(self._current_piece)
        if not isinstance(p, GUIHumanPlayer): return
        with self._lock:
            snap = self._board_snap
        if not snap or not snap.is_valid_move(row,col): return
        p.submit_move(row,col)

    def _add_skill_fx(self, skill_type: str, row: int, col: int):
        cx,cy = self._bd2px(row, col)
        self._skill_fx.append((skill_type, cx, cy, time.time()))

    # ─────────────────────────────────────────────────────────
    # 渲染主入口
    # ─────────────────────────────────────────────────────────
    def _draw_frame(self):
        t = time.time()-self._t0
        self._screen.fill(C.GUI_COLOR_BG)
        self._draw_board_area()
        self._draw_grid()
        self._draw_pieces(t)
        self._draw_skill_fx(t)
        if self._win_line: self._draw_win_line()
        if self._last_move and not self._game_over: self._draw_last_marker(t)
        if not self._game_over: self._draw_hover(t)
        self._draw_panel(t)
        if self._game_over: self._draw_result(t)

    def _draw_board_area(self):
        self._screen.blit(self._board_tex, (0,0))
        r=pygame.Rect(_ORIGIN_X-_CELL//2-4,_ORIGIN_Y-_CELL//2-4,
                      _CELL*(C.BOARD_SIZE-1)+_CELL+8,_CELL*(C.BOARD_SIZE-1)+_CELL+8)
        pygame.draw.rect(self._screen, C.GUI_COLOR_BOARD_DARK, r, 3, border_radius=4)

    def _draw_grid(self):
        sz=C.BOARD_SIZE; cl=C.GUI_COLOR_GRID_LINE
        for i in range(sz):
            pygame.draw.line(self._screen,cl,(_ORIGIN_X,_ORIGIN_Y+i*_CELL),(_ORIGIN_X+(sz-1)*_CELL,_ORIGIN_Y+i*_CELL),1)
            pygame.draw.line(self._screen,cl,(_ORIGIN_X+i*_CELL,_ORIGIN_Y),(_ORIGIN_X+i*_CELL,_ORIGIN_Y+(sz-1)*_CELL),1)
        pygame.draw.rect(self._screen,cl,(_ORIGIN_X,_ORIGIN_Y,(sz-1)*_CELL,(sz-1)*_CELL),2)
        stars=[(3,3),(3,11),(7,7),(11,3),(11,11)] if sz==15 else ([(sz//2,sz//2)] if sz>=9 else [])
        for sr,sc in stars:
            px,py=self._bd2px(sr,sc)
            pygame.gfxdraw.filled_circle(self._screen,px,py,4,C.GUI_COLOR_STAR_DOT)
            pygame.gfxdraw.aacircle(self._screen,px,py,4,C.GUI_COLOR_STAR_DOT)
        for i in range(sz):
            x,_=self._bd2px(0,i); lb=self._fc.render(str(i),True,C.GUI_COLOR_COORD)
            self._screen.blit(lb,(x-lb.get_width()//2,_ORIGIN_Y-_CELL//2-lb.get_height()-2))
            _,y=self._bd2px(i,0); lb=self._fc.render(str(i),True,C.GUI_COLOR_COORD)
            self._screen.blit(lb,(_ORIGIN_X-_CELL//2-lb.get_width()-4,y-lb.get_height()//2))

    def _draw_pieces(self, t):
        with self._lock:
            snap=self._board_snap; anims=list(self._drop_anims)
        if not snap: return
        now=time.time()
        anim_coords=set()
        for r,c,piece,st in anims:
            if (now-st)<self._DROP_DUR: anim_coords.add((r,c))

        # 技能高亮：乾坤挪移时高亮对手棋子，终归虚无高亮所有棋子
        highlight_opp = (self._skill_mode=="swap")
        highlight_void = (self._skill_mode=="void")
        opp_piece = C.WHITE if self._current_piece==C.BLACK else C.BLACK

        for r in range(snap.size):
            for c in range(snap.size):
                piece=snap.get(r,c)
                if piece!=C.EMPTY and (r,c) not in anim_coords:
                    cx,cy=self._bd2px(r,c)
                    if highlight_opp and piece==opp_piece:
                        # 高亮对手棋子：添加金色光圈
                        tmp=pygame.Surface((_BOARD_AREA_W,_BOARD_AREA_H),pygame.SRCALPHA)
                        pulse=abs(math.sin(t*4))*60+120
                        pygame.gfxdraw.aacircle(tmp,cx,cy,_PIECE_R+4,(255,200,50,int(pulse)))
                        pygame.gfxdraw.filled_circle(tmp,cx,cy,_PIECE_R+4,(255,200,50,40))
                        self._screen.blit(tmp,(0,0))
                    if highlight_void:
                        # 淡化棋盘棋子
                        self._blit_piece(self._screen,cx,cy,_PIECE_R,piece,160)
                    else:
                        self._blit_piece(self._screen,cx,cy,_PIECE_R,piece,255)

        # 终归虚无高亮：悬停格的 3×3
        if highlight_void and self._hover:
            hr,hc=self._hover
            tmp=pygame.Surface((_BOARD_AREA_W,_BOARD_AREA_H),pygame.SRCALPHA)
            pulse=int(abs(math.sin(t*3))*60+80)
            for dr in range(-1,2):
                for dc in range(-1,2):
                    nr,nc=hr+dr,hc+dc
                    if 0<=nr<snap.size and 0<=nc<snap.size:
                        ex,ey=self._bd2px(nr,nc)
                        rect=pygame.Rect(ex-_CELL//2,ey-_CELL//2,_CELL,_CELL)
                        pygame.draw.rect(tmp,(180,80,255,pulse),rect,border_radius=4)
            self._screen.blit(tmp,(0,0))

        # 一马当先：高亮已选第一落点
        if self._skill_mode=="horse_second" and self._horse_first:
            r1,c1=self._horse_first
            cx,cy=self._bd2px(r1,c1)
            tmp=pygame.Surface((_BOARD_AREA_W,_BOARD_AREA_H),pygame.SRCALPHA)
            pulse=int(abs(math.sin(t*4))*80+120)
            pygame.gfxdraw.filled_circle(tmp,cx,cy,_PIECE_R+3,(100,200,255,pulse))
            pygame.gfxdraw.aacircle(tmp,cx,cy,_PIECE_R+3,(100,200,255,220))
            self._screen.blit(tmp,(0,0))
            # 显示4个可选斜方向
            for dr,dc in [(-1,-1),(-1,1),(1,-1),(1,1)]:
                nr,nc=r1+dr,c1+dc
                with self._lock:
                    snap2=self._board_snap
                if snap2 and 0<=nr<snap2.size and 0<=nc<snap2.size and snap2.is_valid_move(nr,nc):
                    ex,ey=self._bd2px(nr,nc)
                    tmp2=pygame.Surface((_BOARD_AREA_W,_BOARD_AREA_H),pygame.SRCALPHA)
                    pygame.gfxdraw.filled_circle(tmp2,ex,ey,_PIECE_R,(100,200,255,80))
                    pygame.gfxdraw.aacircle(tmp2,ex,ey,_PIECE_R,(100,200,255,160))
                    self._screen.blit(tmp2,(0,0))

        # 动画棋子
        new_anims=[]
        for r,c,piece,st in anims:
            elapsed=now-st
            if elapsed>=self._DROP_DUR: continue
            new_anims.append((r,c,piece,st))
            cx,target_y=self._bd2px(r,c); progress=elapsed/self._DROP_DUR
            if progress<0.6:
                p=progress/0.6; ease=p*p; start_y=_ORIGIN_Y-_CELL*3
                cy=int(start_y+(target_y-start_y)*ease)
            elif progress<0.8:
                p=(progress-0.6)/0.2; cy=int(target_y-_CELL*0.4*math.sin(p*math.pi))
            else:
                cy=target_y
            scale=1.0 if progress<0.6 else (1.0+0.15*math.sin((progress-0.6)/0.4*math.pi))
            rad=int(_PIECE_R*scale)
            self._blit_piece(self._screen,cx,cy,rad,piece,255)
        with self._lock: self._drop_anims=new_anims

    def _blit_piece(self,surf,cx,cy,radius,piece,alpha=255):
        owner=self._piece_owner.get(piece,None)
        img_src=None
        if owner=="player" and self._piece_img_player: img_src=self._piece_img_player
        elif owner=="ai" and self._piece_img_ai: img_src=self._piece_img_ai
        if img_src is not None:
            key=(owner,radius)
            if key not in self._piece_img_cache:
                d=radius*2; scaled=pygame.transform.smoothscale(img_src,(d,d))
                mask=pygame.Surface((d,d),pygame.SRCALPHA); mask.fill((0,0,0,0))
                pygame.gfxdraw.filled_circle(mask,radius,radius,radius-1,(255,255,255,255))
                result=pygame.Surface((d,d),pygame.SRCALPHA); result.blit(scaled,(0,0))
                result.blit(mask,(0,0),special_flags=pygame.BLEND_RGBA_MIN)
                self._piece_img_cache[key]=result
            img=self._piece_img_cache[key]
            if alpha<255: img=img.copy(); img.set_alpha(alpha)
            surf.blit(img,(cx-radius,cy-radius))
        else:
            _draw_piece(surf,cx,cy,radius,piece==C.BLACK,alpha)

    def _draw_skill_fx(self, t):
        """绘制技能特效动画。"""
        now=time.time(); dur=0.6; new_fx=[]
        tmp=pygame.Surface((_BOARD_AREA_W,_BOARD_AREA_H),pygame.SRCALPHA)
        for sk,cx,cy,st in self._skill_fx:
            el=now-st
            if el>=dur: continue
            new_fx.append((sk,cx,cy,st)); p=el/dur
            color=_SKILL_COLORS.get(sk,(255,255,255))
            if sk=="horse":
                # 从上掉落闪光
                rad=int(_PIECE_R*(1.5-p)); a=int(255*(1-p))
                for w,fa in [(rad+8,30),(rad+4,70),(rad,a)]:
                    if w>0: pygame.gfxdraw.aacircle(tmp,cx,cy,w,(*color,fa))
            elif sk=="swap":
                # 旋转光环
                for i in range(8):
                    angle=i*math.pi/4+p*math.pi*4
                    rx=int(cx+(_PIECE_R+6)*math.cos(angle)); ry=int(cy+(_PIECE_R+6)*math.sin(angle))
                    a=int(200*(1-p))
                    pygame.gfxdraw.filled_circle(tmp,rx,ry,4,(*color,a))
                a=int(180*(1-p)); pygame.gfxdraw.aacircle(tmp,cx,cy,_PIECE_R+4,(*color,a))
            elif sk=="void":
                # 向外扩散的方形波纹
                sz=int((_PIECE_R*4)*p); a=int(200*(1-p))
                if sz>0:
                    rect=pygame.Rect(cx-sz//2,cy-sz//2,sz,sz)
                    pygame.draw.rect(tmp,(*color,a),rect,3,border_radius=6)
        self._screen.blit(tmp,(0,0))
        self._skill_fx=new_fx

    def _draw_last_marker(self,t):
        if not self._last_move: return
        r,c=self._last_move; cx,cy=self._bd2px(r,c)
        pulse=abs(math.sin(t*3.5)); rad=int(_PIECE_R*(0.35+0.2*pulse)); alpha=int(180+60*pulse)
        tmp=pygame.Surface((_BOARD_AREA_W,_BOARD_AREA_H),pygame.SRCALPHA)
        pygame.gfxdraw.aacircle(tmp,cx,cy,rad,(*C.GUI_COLOR_LAST_MOVE,alpha))
        pygame.gfxdraw.aacircle(tmp,cx,cy,rad+1,(*C.GUI_COLOR_LAST_MOVE,alpha//2))
        self._screen.blit(tmp,(0,0))

    def _draw_hover(self,t):
        if not self._hover: return
        from agents.gui_human import GUIHumanPlayer
        if not self._engine_ref: return
        p=self._engine_ref._players.get(self._current_piece)
        if not isinstance(p,GUIHumanPlayer): return
        r,c=self._hover
        with self._lock: snap=self._board_snap
        if self._skill_mode: return  # 技能模式下不显示悬停预览
        if not snap or not snap.is_valid_move(r,c): return
        cx,cy=self._bd2px(r,c)
        tmp=pygame.Surface((_BOARD_AREA_W,_BOARD_AREA_H),pygame.SRCALPHA)
        _draw_piece(tmp,cx,cy,_PIECE_R,self._current_piece==C.BLACK,90)
        self._screen.blit(tmp,(0,0))

    def _detect_win_line(self,board):
        if not self._last_move: return
        row,col=self._last_move; piece=board.get(row,col)
        if piece==C.EMPTY: return
        for dr,dc in [(0,1),(1,0),(1,1),(1,-1)]:
            cells=[(row,col)]
            for sign in (1,-1):
                r,c=row+sign*dr,col+sign*dc
                while 0<=r<board.size and 0<=c<board.size and board.get(r,c)==piece:
                    cells.append((r,c)); r+=sign*dr; c+=sign*dc
            if len(cells)>=C.WIN_COUNT:
                cells.sort(); self._win_line=[cells[0],cells[-1]]; return

    def _draw_win_line(self):
        if not self._win_line: return
        _glow_line(self._screen,self._bd2px(*self._win_line[0]),self._bd2px(*self._win_line[1]),C.GUI_COLOR_WIN_LINE,4)

    # ─────────────────────────────────────────────────────────
    # 侧边栏（含技能按钮）
    # ─────────────────────────────────────────────────────────
    def _draw_panel(self,t):
        px=_BOARD_AREA_W; pw=C.GUI_SIDE_PANEL_W; ph=C.GUI_WINDOW_H
        ps=pygame.Surface((pw,ph),pygame.SRCALPHA); ps.fill((*C.GUI_COLOR_PANEL_BG,240))
        self._screen.blit(ps,(px,0))
        pygame.draw.line(self._screen,C.GUI_COLOR_PANEL_BORDER,(px,0),(px,ph),2)
        y=20
        ti=self._ft.render("五子棋",True,C.GUI_COLOR_ACCENT)
        self._screen.blit(ti,(px+(pw-ti.get_width())//2,y)); y+=36
        su=self._fs.render("G O B A N G",True,C.GUI_COLOR_TEXT_DIM)
        self._screen.blit(su,(px+(pw-su.get_width())//2,y)); y+=26
        pygame.draw.line(self._screen,C.GUI_COLOR_PANEL_BORDER,(px+15,y),(px+pw-15,y),1); y+=14

        # 当前回合
        if not self._game_over:
            cp=self._current_piece; pn=C.PIECE_NAMES[cp]
            cd=C.GUI_BLACK_BASE if cp==C.BLACK else C.GUI_WHITE_BASE
            pulse=abs(math.sin(t*2.5)); dr=int(7+3*pulse)
            pygame.gfxdraw.filled_circle(self._screen,px+24,y+11,dr,cd)
            pygame.gfxdraw.aacircle(self._screen,px+24,y+11,dr,C.GUI_COLOR_ACCENT)
            tt=self._fn.render(f"{pn}回合",True,C.GUI_COLOR_TEXT_MAIN)
            self._screen.blit(tt,(px+40,y)); y+=32
            if self._ai_thinking:
                dots="●"*(int(t*2)%4)
                at=self._fs.render(f"AI 思考中{dots}",True,C.GUI_COLOR_TEXT_DIM)
                self._screen.blit(at,(px+18,y)); y+=20
        y+=4
        if self._engine_ref:
            for piece,player in [(C.BLACK,self._engine_ref._players[C.BLACK]),(C.WHITE,self._engine_ref._players[C.WHITE])]:
                dc=(40,40,40) if piece==C.BLACK else (230,230,220)
                pygame.gfxdraw.filled_circle(self._screen,px+18,y+9,8,dc)
                pygame.gfxdraw.aacircle(self._screen,px+18,y+9,8,(120,90,40))
                ns=self._fs.render(player.name[:12],True,C.GUI_COLOR_TEXT_MAIN)
                self._screen.blit(ns,(px+34,y)); y+=22
        y+=6
        mt=self._fs.render(f"第 {self._move_count} 手",True,C.GUI_COLOR_TEXT_DIM)
        self._screen.blit(mt,(px+18,y)); y+=20
        pygame.draw.line(self._screen,C.GUI_COLOR_PANEL_BORDER,(px+15,y),(px+pw-15,y),1); y+=10

        # 状态消息
        for ln in self._wrap(self._message,self._fs,pw-28):
            s=self._fs.render(ln,True,C.GUI_COLOR_TEXT_DIM)
            self._screen.blit(s,(px+14,y)); y+=18
        y+=4

        # ── 技能区 ────────────────────────────────────────────
        is_human = self._is_human_turn()
        pygame.draw.line(self._screen,C.GUI_COLOR_PANEL_BORDER,(px+15,y),(px+pw-15,y),1); y+=10

        skill_label=self._fs.render("── 特殊能力 ──",True,C.GUI_COLOR_ACCENT)
        self._screen.blit(skill_label,(px+(pw-skill_label.get_width())//2,y)); y+=20

        self._btn_rects = {}
        btn_w=pw-24; btn_h=38; mgap=6

        # 悔棋按钮
        undo_rect=pygame.Rect(px+12,y,btn_w,btn_h)
        self._btn_rects["undo"]=undo_rect
        self._draw_btn(undo_rect,"↩ 悔棋","Z键",is_human,None,t)
        y+=btn_h+mgap

        # 三个技能按钮
        charges = self._engine_ref.skill_charges if self._engine_ref else {"horse":0,"swap":0,"void":0}
        for sk in ("horse","swap","void"):
            ch=charges.get(sk,0)
            active=(self._skill_mode in (sk,"horse_first","horse_second") and sk=="horse") or self._skill_mode==sk
            rect=pygame.Rect(px+12,y,btn_w,btn_h)
            self._btn_rects[sk]=rect
            label=f"{'▶ ' if active else ''}{_SKILL_NAMES[sk]}"
            sub=_SKILL_DESCS[sk]
            available = is_human and ch>0 and not self._game_over
            key_color=_SKILL_COLORS[sk] if available else C.GUI_COLOR_TEXT_DIM
            self._draw_skill_btn(rect, label, sub, available, active, key_color, t, sk)
            y+=btn_h+mgap

        # 底部按键提示
        for i,h in enumerate(["ESC  取消技能/退出","Z键  悔棋","点击落子"]):
            s=self._fxs.render(h,True,C.GUI_COLOR_TEXT_DIM)
            self._screen.blit(s,(px+14,ph-56+i*18))

    def _draw_btn(self,rect,label,sublabel,enabled,color,t):
        surf=pygame.Surface((rect.w,rect.h),pygame.SRCALPHA)
        if enabled:
            bg=(*C.GUI_COLOR_PANEL_BORDER,120); bc=C.GUI_COLOR_TEXT_DIM
        else:
            bg=(*C.GUI_COLOR_PANEL_BG,80); bc=(50,40,30)
        pygame.draw.rect(surf,bg,(0,0,rect.w,rect.h),border_radius=8)
        pygame.draw.rect(surf,(*bc,180),(0,0,rect.w,rect.h),1,border_radius=8)
        self._screen.blit(surf,(rect.x,rect.y))
        lc=C.GUI_COLOR_TEXT_MAIN if enabled else (70,60,50)
        lt=self._fs.render(label,True,lc)
        self._screen.blit(lt,(rect.x+(rect.w-lt.get_width())//2,rect.y+4))
        if sublabel:
            sc2=(90,80,60) if enabled else (50,40,30)
            st=self._fxs.render(sublabel,True,sc2)
            self._screen.blit(st,(rect.x+(rect.w-st.get_width())//2,rect.y+22))

    def _draw_skill_btn(self,rect,label,sublabel,enabled,active,color,t,sk):
        surf=pygame.Surface((rect.w,rect.h),pygame.SRCALPHA)
        # color 约定为 3 元素 RGB tuple
        if active:
            bg=(*tuple(int(c*0.3) for c in color),200)
            bc=(*color, 220)   # 4 元素 RGBA
        elif enabled:
            bg=(*C.GUI_COLOR_PANEL_BG,160)
            bc=(*color, 160)   # 4 元素 RGBA
        else:
            bg=(*C.GUI_COLOR_PANEL_BG,80)
            bc=(50, 40, 30, 180)  # 4 元素 RGBA
        pygame.draw.rect(surf, bg, (0,0,rect.w,rect.h), border_radius=8)
        border_w=2 if active else 1
        pygame.draw.rect(surf, bc, (0,0,rect.w,rect.h), border_w, border_radius=8)
        self._screen.blit(surf,(rect.x,rect.y))
        lc=color if (enabled or active) else (70,60,50)
        lt=self._fs.render(label,True,lc)
        self._screen.blit(lt,(rect.x+8,rect.y+4))
        sc2=tuple(min(255,c+80) for c in color) if enabled else (50,40,30)
        st=self._fxs.render(sublabel,True,sc2)
        self._screen.blit(st,(rect.x+8,rect.y+22))

    # ─────────────────────────────────────────────────────────
    # 结果弹窗
    # ─────────────────────────────────────────────────────────
    def _draw_result(self,t):
        self._overlay_a=min(self._overlay_a+4,160)
        ov=pygame.Surface((C.GUI_WINDOW_W,C.GUI_WINDOW_H),pygame.SRCALPHA)
        ov.fill((0,0,0,self._overlay_a)); self._screen.blit(ov,(0,0))
        if self._overlay_a<80: return
        cw,ch=480,220; cx=(C.GUI_WINDOW_W-cw)//2; cy=(C.GUI_WINDOW_H-ch)//2
        card=pygame.Surface((cw,ch),pygame.SRCALPHA)
        pygame.draw.rect(card,(*C.GUI_COLOR_PANEL_BG,230),(0,0,cw,ch),border_radius=18)
        pygame.draw.rect(card,(*C.GUI_COLOR_ACCENT,200),(0,0,cw,ch),3,border_radius=18)
        self._screen.blit(card,(cx,cy))
        clean=self._game_result.lstrip().lstrip("🎉🤝 \n")
        pulse=abs(math.sin(t*2))
        tc=tuple(int(c*(0.85+0.15*pulse)) for c in C.GUI_COLOR_ACCENT)
        ts=self._fl.render("游戏结束",True,tc)
        self._screen.blit(ts,(cx+(cw-ts.get_width())//2,cy+35))
        for i,ln in enumerate(self._wrap(clean,self._fn,cw-40)):
            s=self._fn.render(ln,True,C.GUI_COLOR_TEXT_MAIN)
            self._screen.blit(s,(cx+(cw-s.get_width())//2,cy+110+i*28))
        ht=self._fs.render("按 ESC 退出",True,C.GUI_COLOR_TEXT_DIM)
        self._screen.blit(ht,(cx+(cw-ht.get_width())//2,cy+ch-35))
        if "获胜" in self._game_result:
            tmp=pygame.Surface((C.GUI_WINDOW_W,C.GUI_WINDOW_H),pygame.SRCALPHA)
            cols=[(255,215,0),(255,100,100),(100,200,255),(180,255,100),(255,150,50)]
            rng=random.Random(42)
            for i in range(40):
                st=t+i*0.3
                x=int((rng.random()*C.GUI_WINDOW_W+st*80*rng.choice([-1,1]))%C.GUI_WINDOW_W)
                y=int((i*47+st*120)%C.GUI_WINDOW_H)
                r=rng.randint(3,7); a=int(160*abs(math.sin(t*2+i)))
                pygame.gfxdraw.filled_circle(tmp,x,y,r,(*cols[i%5],a))
            self._screen.blit(tmp,(0,0))

    # ─────────────────────────────────────────────────────────
    # 工具
    # ─────────────────────────────────────────────────────────
    @staticmethod
    def _lf(size, bold=False):
        """加载支持中文的字体，优先用文件路径直接加载（避免 SysFont 名字查找失败）。"""
        pygame.font.init()
        # 优先尝试文件路径加载（Linux 系统常见位置）
        font_paths = [
            # Noto Sans CJK（简体中文最佳）
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            # Arphic（备用）
            "/usr/share/fonts/truetype/arphic/uming.ttc",
            "/usr/share/fonts/truetype/arphic/ukai.ttc",
            # macOS
            "/System/Library/Fonts/PingFang.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
            # Windows
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
        ]
        for path in font_paths:
            import os
            if os.path.isfile(path):
                try:
                    f = pygame.font.Font(path, size)
                    if f.render("测", True, (255,255,255)).get_width() > 4:
                        return f
                except Exception:
                    continue
        # 回退：SysFont
        for n in ["notosanscjk","notosanssc","wqymicrohei","SimHei","NotoSansCJK"]:
            try:
                f = pygame.font.SysFont(n, size, bold=bold)
                if f.render("测", True, (255,255,255)).get_width() > 4:
                    return f
            except Exception:
                continue
        return pygame.font.SysFont(None, size, bold=bold)

    @staticmethod
    def _wrap(text,font,max_w):
        lines=[]
        for p in text.split("\n"):
            p=p.strip()
            if not p: continue
            cur=""
            for ch in p:
                if font.size(cur+ch)[0]<=max_w: cur+=ch
                else:
                    if cur: lines.append(cur)
                    cur=ch
            if cur: lines.append(cur)
        return lines or [text[:30]]

    @staticmethod
    def _load_piece_img(path):
        if not os.path.isfile(path):
            print(f"  [GUIView] 棋子图片未找到：{path}"); return None
        try: return pygame.image.load(path).convert_alpha()
        except Exception as e: print(f"  [GUIView] 图片加载失败：{e}"); return None

    @staticmethod
    def _load_sound(path):
        if not os.path.isfile(path):
            print(f"  [GUIView] 音效未找到：{path}"); return None
        try: return pygame.mixer.Sound(path)
        except Exception as e: print(f"  [GUIView] 音效加载失败：{e}"); return None
