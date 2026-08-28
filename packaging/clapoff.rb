# Homebrew formula for clapoff.
#
# NOT USABLE YET. The url below points at a PyPI sdist that does not exist until
# the first release, and the `resource` stanzas for numpy/sounddevice have to be
# generated from that sdist with:
#
#     brew update-python-resources packaging/clapoff.rb
#
# Shipping a formula with invented hashes would fail at install time with a
# checksum mismatch, which is a much worse experience than this comment.
class Clapoff < Formula
  include Language::Python::Virtualenv

  desc "Turn off your computer by clapping at it"
  homepage "https://github.com/jeranaias/clapoff"
  url "https://files.pythonhosted.org/packages/source/c/clapoff/clapoff-0.1.0.tar.gz"
  sha256 "0" * 64  # replaced at release time; see above
  license "MIT"

  depends_on "portaudio"
  depends_on "python@3.12"

  # resource stanzas go here - generate them, don't write them by hand

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "clapoff", shell_output("#{bin}/clapoff --version")
  end
end
