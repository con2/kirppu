(function () {
    const CLS = "yv8k02zi";
    const KEY = "yJrx6Rvvyn39u4La";

    $(document).ready(() => {
        $("." + CLS).each(function() {
            try {
                const str = atob(this.innerText);
                let dec = "";
                for (let i = 0; i < str.length; i++) {
                    dec += String.fromCodePoint(str.codePointAt(i) ^ KEY.codePointAt(i % KEY.length));
                }
                $(this).removeClass(CLS);
                this.innerHTML = dec;
            } catch (e) {
                this.innerText = "<error>";
            }
        });
    });
})();
