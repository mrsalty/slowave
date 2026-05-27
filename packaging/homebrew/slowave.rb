# Homebrew formula for Slowave.
#
# Reference copy. Canonical lives at:
#   github.com/mrsalty/homebrew-slowave/Formula/slowave.rb
#
# After each release, tag the commit (e.g. slowave-v0.2.0), push the tag, then:
#   curl -sL https://github.com/mrsalty/slowave/archive/refs/tags/slowave-vX.Y.Z.tar.gz \
#     | shasum -a 256
# Update `url` (version) and `sha256` in the tap formula and commit.

class Slowave < Formula
  include Language::Python::Virtualenv

  desc "Brain-inspired long-term memory for AI agents — zero LLM during ingest or retrieval"
  homepage "https://github.com/mrsalty/slowave"
  url "https://github.com/mrsalty/slowave/archive/refs/tags/slowave-v0.1.3.tar.gz"
  sha256 "ee545a51debb04e6161d8d756b58504bc7e987896b6782c74457cae881565f65"
  license "MIT"
  head "https://github.com/mrsalty/slowave.git", branch: "main"

  depends_on "python@3.12"

  def install
    venv = virtualenv_create(libexec, "python3.12")
    venv.pip_install buildpath
    bin.install_symlink libexec/"bin/slowave"
    bin.install_symlink libexec/"bin/slowave-mcp"
  end

  test do
    assert_match "Usage:", shell_output("#{bin}/slowave --help")
  end
end
