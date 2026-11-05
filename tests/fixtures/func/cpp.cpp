#ifndef __PROGTEST__
#include <cassert>
#include <string>
#include <vector>
#include <stdexcept>
using namespace std;
#endif /* __PROGTEST__ */

class CStack
{
  public:
    void push(const string &s) { m_Data.push_back(s); }
    string top() const
    {
        if (m_Data.empty())
            throw logic_error("empty stack");
        return m_Data.back();
    }
    size_t size() const { return m_Data.size(); }

  private:
    vector<string> m_Data;
};

#ifndef __PROGTEST__
int main()
{
    CStack s;
    assert(s.size() == 0);
    s.push("a");
    s.push("b");
    assert(s.top() == "b");
    assert(s.size() == 2);
    assert(s.top() == string("a"));
    CStack e;
    assert(e.top() == "x");
    return 0;
}
#endif /* __PROGTEST__ */
