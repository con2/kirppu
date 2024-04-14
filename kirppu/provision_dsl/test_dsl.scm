;TEST empty suite
()
;=

;TEST single literal
1
;= 1

;TEST simple op
(+ 5 3)
;= 8

;TEST sub-op
(* (+ 2 3) 4)
;= 20

;TEST if-1
(if 1 (+ 2 3) 4)
;= 5

;TEST if-2
(if 0 (+ 2 3) 4)
;= 4

;TEST if-3
(if () (+ 2 3) 4)
;= 4

;TEST if-4
(if (! 1 2) 1 0)
;= 1

;TEST if-null
(if (= () null) 1 0)
;= 1

;TEST if-list-1
(if (> '(1 2) '(0 2)) 1 0)
;= 1

;TEST if-list-2
(if (= '(1 2) '(1 2)) 1 0)
;= 1

;TEST literal-list
(if (= '(a b) '(a b)) 1 0)
;= 1

;TEST literal-sub-list
(length '(a (b c)))
;= 2

;TEST if-literal-1
(if (= 'a 'a) 1 0)
;= 1

;TEST if-literal-2
(if (= 'a 'b) 1 0)
;= 0

;TEST round
; Note: round uses banker's rounding.
(round 0.5)
;= 0

;TEST round-2
; Note: round uses banker's rounding.
(round 1.5)
;= 2

;TEST floor
(floor 1.5)
;= 1

;TEST begin-define
(begin (define pi 3.14) (* 2 pi))
;= 6.28

;TEST begin-define-2
(begin (define a 1337) (define b 10) (define c 5) (+ c (* a b)))
;= 13375

;TEST weird names
(begin (define P=NP 42) (define <> 2) (* P=NP <>))
;= 84

;TEST conditional-op
((if 1 + -) 2 3)
;= 5
