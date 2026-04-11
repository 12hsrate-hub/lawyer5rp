window.OGPPage = {
  showOptionalText(host, text) {
    if (!text) {
      window.OGPWeb.clearText(host);
      return;
    }
    window.OGPWeb.showText(host, text);
  },

  bindLogout(button, { message = "Вы вышли из аккаунта." } = {}) {
    if (!button) {
      return;
    }
    button.addEventListener("click", async () => {
      await window.OGPWeb.apiFetch("/api/auth/logout", { method: "POST" });
      sessionStorage.setItem("ogp_auth_message", message);
      location.href = "/login";
    });
  },

  bindSectionJump(navElement) {
    if (!navElement) {
      return;
    }
    const links = [...navElement.querySelectorAll("a[href^='#']")];
    if (!links.length) {
      return;
    }

    const sections = links
      .map((link) => {
        const id = (link.getAttribute("href") || "").slice(1);
        if (!id) {
          return null;
        }
        const section = document.getElementById(id);
        if (!section) {
          return null;
        }
        return { link, section };
      })
      .filter(Boolean);

    if (!sections.length) {
      return;
    }

    const setActive = (currentId) => {
      sections.forEach(({ link, section }) => {
        const isActive = section.id === currentId;
        link.classList.toggle("is-active", isActive);
        link.setAttribute("aria-current", isActive ? "true" : "false");
      });
    };

    sections.forEach(({ link, section }) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        section.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible?.target?.id) {
          setActive(visible.target.id);
        }
      },
      {
        rootMargin: "-20% 0px -65% 0px",
        threshold: [0.2, 0.45, 0.7],
      },
    );

    sections.forEach(({ section }) => observer.observe(section));
    setActive(sections[0].section.id);
  },
};

document.querySelectorAll(".legal-section-jump").forEach((navElement) => {
  window.OGPPage.bindSectionJump(navElement);
});
